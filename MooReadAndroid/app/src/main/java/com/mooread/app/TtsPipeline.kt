package com.mooread.app

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import com.k2fsa.sherpa.onnx.GeneratedAudio
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsKokoroModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import kotlin.concurrent.thread

/**
 * Bundled Kokoro-82M int8 via sherpa-onnx.
 * Model files live in APK assets/kokoro — nothing is downloaded.
 * HOT + WARM wav cache only.
 */
class TtsPipeline(private val context: Context) {
    data class Speaker(val sid: Int, val name: String)

    companion object {
        val SPEAKERS = listOf(
            Speaker(0, "af_alloy"),
            Speaker(1, "af_aoede"),
            Speaker(2, "af_bella"),
            Speaker(3, "af_heart"),
            Speaker(4, "af_jessica"),
            Speaker(5, "af_kore"),
            Speaker(6, "af_nicole"),
            Speaker(7, "af_nova"),
            Speaker(8, "af_river"),
            Speaker(9, "af_sarah"),
            Speaker(10, "af_sky"),
            Speaker(11, "am_adam"),
            Speaker(12, "am_echo"),
            Speaker(13, "am_eric"),
            Speaker(14, "am_fenrir"),
            Speaker(15, "am_liam"),
            Speaker(16, "am_michael"),
            Speaker(17, "am_onyx"),
            Speaker(18, "am_puck"),
            Speaker(19, "am_santa"),
            Speaker(20, "bf_alice"),
            Speaker(21, "bf_emma"),
            Speaker(22, "bf_isabella"),
            Speaker(23, "bf_lily"),
            Speaker(24, "bm_daniel"),
            Speaker(25, "bm_fable"),
            Speaker(26, "bm_george"),
            Speaker(27, "bm_lewis"),
            Speaker(28, "ef_dora"),
            Speaker(29, "em_alex"),
            Speaker(30, "ff_siwis"),
            Speaker(31, "hf_alpha"),
            Speaker(32, "hf_beta"),
            Speaker(33, "hm_omega"),
            Speaker(34, "hm_psi"),
            Speaker(35, "if_sara"),
            Speaker(36, "im_nicola"),
            Speaker(37, "jf_alpha"),
            Speaker(38, "jf_gongitsune"),
            Speaker(39, "jf_nezumi"),
            Speaker(40, "jf_tebukuro"),
            Speaker(41, "jm_kumo"),
            Speaker(42, "pf_dora"),
            Speaker(43, "pm_alex"),
            Speaker(44, "pm_santa"),
            Speaker(45, "zf_xiaobei"),
            Speaker(46, "zf_xiaoni"),
            Speaker(47, "zf_xiaoxiao"),
            Speaker(48, "zf_xiaoyi"),
            Speaker(49, "zm_yunjian"),
            Speaker(50, "zm_yunxi"),
            Speaker(51, "zm_yunxia"),
            Speaker(52, "zm_yunyang"),
            Speaker(53, "em_santa")
        )
    }

    @Volatile var readyEngine = false
        private set
    @Volatile var currentIndex = 0
    @Volatile var looping = false
    @Volatile var playing = false
    var chunks: List<String> = emptyList()
    var source: SpeechSource? = null
    var profile: VoiceProfile = VoiceProfiles.builtin().first()
    var onStartChunk: ((Int, String) -> Unit)? = null
    var onDoneAll: (() -> Unit)? = null
    var onStatus: ((String) -> Unit)? = null

    private val cache = File(context.cacheDir, "mooread-audio").apply { mkdirs() }
    private val ready = ConcurrentHashMap<Int, File>()
    private val readyAudio = ConcurrentHashMap<Int, GeneratedAudio>()
    private var tts: OfflineTts? = null
    private var track: AudioTrack? = null
    private val synthLock = Any()
    @Volatile private var workerAlive = false
    @Volatile private var warmAlive = false
    @Volatile private var warmStop = false
    @Volatile private var warmGen = 0
    private val ahead = 5

    fun initEngine(): String {
        return try {
            val dest = File(context.filesDir, "kokoro")
            copyAssetDir("kokoro", dest)
            val lexEn = File(dest, "lexicon-us-en.txt")
            val lexZh = File(dest, "lexicon-zh.txt")
            val lexicon = listOf(lexEn, lexZh).filter { it.exists() }.joinToString(",") { it.absolutePath }
            val kokoro = OfflineTtsKokoroModelConfig(
                model = File(dest, "model.int8.onnx").absolutePath,
                voices = File(dest, "voices.bin").absolutePath,
                tokens = File(dest, "tokens.txt").absolutePath,
                dataDir = File(dest, "espeak-ng-data").absolutePath,
                lexicon = lexicon,
                lang = "",
                dictDir = "",
                lengthScale = 1.0f
            )
            val model = OfflineTtsModelConfig(
                vits = com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig(),
                matcha = com.k2fsa.sherpa.onnx.OfflineTtsMatchaModelConfig(),
                kokoro = kokoro,
                kitten = com.k2fsa.sherpa.onnx.OfflineTtsKittenModelConfig(),
                numThreads = 2,
                debug = false,
                provider = "cpu"
            )
            val config = OfflineTtsConfig(
                model = model,
                ruleFsts = "",
                ruleFars = "",
                maxNumSentences = 1,
                silenceScale = 0.2f
            )
            tts = OfflineTts(null, config)
            readyEngine = true
            "Kokoro-82M int8 bundled (${tts?.numSpeakers() ?: 0} speakers)"
        } catch (ex: Throwable) {
            readyEngine = false
            "Voice engine delayed: ${ex.message ?: ex.javaClass.simpleName}"
        }
    }

    private fun copyAssetDir(assetPath: String, dest: File) {
        dest.mkdirs()
        val names = context.assets.list(assetPath) ?: return
        if (names.isEmpty()) {
            return
        }
        for (name in names) {
            val childAsset = "$assetPath/$name"
            val childDest = File(dest, name)
            val kids = context.assets.list(childAsset)
            if (kids != null && kids.isNotEmpty()) {
                copyAssetDir(childAsset, childDest)
            } else {
                if (childDest.exists() && childDest.length() > 0L && !assetFileStale(name, childDest)) continue
                context.assets.open(childAsset).use { input ->
                    childDest.outputStream().use { input.copyTo(it) }
                }
            }
        }
    }

    // Replace English 5.5MB bank, Windows NPZ (PK header), or wrong-sized model.
    // Do NOT treat the sherpa multi-lang voices.bin (~28,200,960 raw floats) as Windows.
    private fun assetFileStale(name: String, dest: File): Boolean {
        if (name == "voices.bin") {
            if (dest.length() < 8_000_000L) return true
            dest.inputStream().use { ins ->
                val magic = ByteArray(2)
                if (ins.read(magic) == 2 && magic[0] == 0x50.toByte() && magic[1] == 0x4B.toByte()) return true
            }
            return dest.length() != 28_200_960L
        }
        if (name == "model.int8.onnx") {
            return dest.length() != 114_203_756L
        }
        if (name == "tokens.txt") {
            return dest.length() != 687L
        }
        return false
    }

    fun load(chunks: List<String>, profile: VoiceProfile, start: Int = 0) {
        stop()
        this.source = null
        this.chunks = chunks
        this.profile = profile
        currentIndex = start.coerceIn(0, (chunks.size - 1).coerceAtLeast(0))
        startWarmer()
    }

    fun loadSource(source: SpeechSource, profile: VoiceProfile, start: Int = 0) {
        stopKeepSource()
        this.source = source
        this.chunks = source.snapshot()
        this.profile = profile
        currentIndex = start.coerceAtLeast(0)
        startWarmer()
    }

    fun hasWork(): Boolean {
        if (source != null) return !source!!.eof || source!!.knownCount() > currentIndex
        return chunks.isNotEmpty()
    }

    fun play() {
        playing = true
        if (!workerAlive) startWorker()
    }

    fun pause() {
        playing = false
        try { track?.pause() } catch (_: Exception) {}
    }

    fun stop() {
        playing = false
        warmStop = true
        warmGen += 1
        try { track?.pause() } catch (_: Exception) {}
        try { track?.flush() } catch (_: Exception) {}
        ready.keys.toList().forEach { drop(it) }
        readyAudio.keys.toList().forEach { readyAudio.remove(it) }
        cache.listFiles()?.forEach { it.delete() }
    }

    private fun stopKeepSource() {
        stop()
    }

    fun next() {
        drop(currentIndex)
        currentIndex += 1
        if (playing) startWorker()
    }

    fun prev() {
        drop(currentIndex)
        currentIndex = (currentIndex - 1).coerceAtLeast(0)
        if (playing) startWorker()
    }

    fun shutdown() {
        stop()
        track?.release()
        tts?.release()
        tts = null
    }

    private fun looksJapanese(text: String): Boolean {
        return text.any { ch ->
            val c = ch.code
            (c in 0x3040..0x30FF) || (c in 0x3400..0x9FFF)
        }
    }

    private fun sid(text: String = ""): Int {
        val maxSid = ((tts?.numSpeakers() ?: 1) - 1).coerceAtLeast(0)
        if (looksJapanese(text)) {
            val jp = SPEAKERS.firstOrNull { it.name == "jf_alpha" }?.sid
            if (jp != null && jp <= maxSid) return jp
        }
        val name = profile.kokoroVoice.ifBlank { profile.androidVoice }
        val picked = SPEAKERS.firstOrNull { it.name.equals(name, true) }?.sid ?: 2
        return picked.coerceIn(0, maxSid)
    }

    private fun textAt(index: Int): String? {
        chunks.getOrNull(index)?.let { return it }
        val src = source ?: return null
        src.ensure(index)
        chunks = src.snapshot()
        return chunks.getOrNull(index)
    }

    private fun startWorker() {
        if (workerAlive) return
        workerAlive = true
        thread(name = "mooread-play") {
            try {
                var waited = 0
                while (playing && !readyEngine && waited++ < 300) Thread.sleep(100)
                if (!readyEngine) {
                    onStatus?.invoke("Voice engine failed to start")
                    playing = false
                    return@thread
                }
                while (playing) {
                    var text = textAt(currentIndex)
                    if (text.isNullOrBlank()) {
                        val src = source
                        if (src != null && !src.eof) {
                            onStatus?.invoke("Reading next page into the voice queue…")
                            src.ensure(currentIndex)
                            chunks = src.snapshot()
                            text = chunks.getOrNull(currentIndex)
                        }
                    }
                    if (!playing) break
                    if (text.isNullOrBlank()) {
                        if (looping && chunks.isNotEmpty()) {
                            currentIndex = 0
                            continue
                        }
                        onStatus?.invoke("End of voice queue at $currentIndex")
                        break
                    }
                    val spoken = VoiceProfiles.applyLexicon(text, profile)
                    onStartChunk?.invoke(currentIndex, spoken)
                    onStatus?.invoke("Speaking ${currentIndex + 1}/${chunks.size.coerceAtLeast(1)} — ${readyAudio.size} prepped")
                    startWarmer()
                    val audio = try {
                        readyAudio.remove(currentIndex) ?: synthesize(spoken)
                    } catch (ex: Exception) {
                        onStatus?.invoke("Synth threw: ${ex.message}")
                        null
                    }
                    if (!playing) break
                    if (audio == null || audio.samples.isEmpty()) {
                        onStatus?.invoke("No audio for block ${currentIndex + 1} — advancing")
                        currentIndex += 1
                        continue
                    }
                    onStatus?.invoke("Playing ${audio.samples.size} samples @ ${audio.sampleRate} Hz")
                    playPcm(audio)
                    currentIndex += 1
                }
                if (playing) {
                    playing = false
                    onDoneAll?.invoke()
                }
            } catch (ex: Exception) {
                onStatus?.invoke("Playback error: ${ex.message}")
            } finally {
                workerAlive = false
            }
        }
        startWarmer()
    }

    private fun startWarmer() {
        warmStop = false
        if (!readyEngine) return
        if (warmAlive) return
        val gen = ++warmGen
        warmAlive = true
        thread(name = "mooread-warm") {
            try {
                while (!warmStop && gen == warmGen) {
                    if (!readyEngine) {
                        Thread.sleep(100)
                        continue
                    }
                    val start = currentIndex
                    val last = start + ahead
                    for (i in start..last) {
                        if (warmStop || gen != warmGen) break
                        if (readyAudio.containsKey(i)) continue
                        val text = textAt(i) ?: break
                        if (text.isBlank()) continue
                        onStatus?.invoke("Preparing ${i + 1} of ${start + ahead + 1} ahead (${readyAudio.size} ready)")
                        val audio = synthesize(VoiceProfiles.applyLexicon(text, profile)) ?: continue
                        readyAudio[i] = audio
                    }
                    readyAudio.keys.filter { it < currentIndex || it > currentIndex + ahead }.forEach { readyAudio.remove(it) }
                    Thread.sleep(80)
                }
            } catch (_: Exception) {
            } finally {
                if (gen == warmGen) warmAlive = false
            }
        }
    }

    private fun synthesize(text: String): GeneratedAudio? {
        val engine = tts ?: return null
        val speed = profile.style.rate.coerceIn(0.7f, 1.4f)
        return synchronized(synthLock) {
            try {
                onStatus?.invoke("Synthesizing block with Kokoro…")
                engine.generate(text, sid(text), speed)
            } catch (ex: Exception) {
                onStatus?.invoke("generate failed: ${ex.message}")
                null
            }
        }
    }

    private fun playPcm(audio: GeneratedAudio) {
        val sr = if (audio.sampleRate > 0) audio.sampleRate else 24000
        val samples = audio.samples
        if (samples.isEmpty()) {
            onStatus?.invoke("Synth produced 0 samples")
            return
        }
        val pcm16 = ShortArray(samples.size) { i ->
            (samples[i].coerceIn(-1f, 1f) * 32767f).toInt().toShort()
        }
        var min = AudioTrack.getMinBufferSize(sr, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) min = sr / 2
        val created = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(sr)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(min * 2)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        track?.release()
        track = created
        created.play()
        var off = 0
        val frame = (min / 2).coerceAtLeast(1024)
        while (off < pcm16.size && playing) {
            val n = created.write(pcm16, off, minOf(frame, pcm16.size - off))
            if (n <= 0) break
            off += n
        }
        try { created.stop() } catch (_: Exception) {}
    }

    private fun drop(index: Int) {
        ready.remove(index)?.delete()
        File(cache, "chunk-$index.wav").delete()
    }

    private fun statusLine(): String {
        val hot = if (ready.containsKey(currentIndex)) "hot:$currentIndex" else "hot:live"
        val warmIdx = currentIndex + 1
        val warm = if (ready.containsKey(warmIdx)) "warm:$warmIdx" else "warm:—"
        val total = source?.knownCount()?.coerceAtLeast(1) ?: chunks.size.coerceAtLeast(1)
        return "$hot  $warm  ${currentIndex + 1}/$total  kokoro"
    }
}
