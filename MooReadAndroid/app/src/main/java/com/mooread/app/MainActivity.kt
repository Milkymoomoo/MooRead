package com.mooread.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import android.view.TextureView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import java.io.File
import java.io.FileOutputStream
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {
    private lateinit var readerView: TextView
    private lateinit var titleView: TextView
    private lateinit var nowPlaying: TextView
    private lateinit var pipeView: TextView
    private lateinit var playBtn: Button
    private lateinit var activityView: TextView
    private lateinit var busyBar: android.widget.ProgressBar
    private lateinit var pipeline: TtsPipeline
    private val ocr = OcrHelper()
    private var profiles = VoiceProfiles.builtin().toMutableList()
    private var currentProfile = profiles.first()
    private var doc: LoadedDoc? = null
    private var speech: SpeechSource? = null
    private var playing = false
    private var translateOn = false
    private var ltrMode = true
    private var themeSnap = mapOf<String, String>()
    private var themeFx: ThemeFxController? = null
    private var wallpaperTilt: WallpaperTilt? = null
    private var wallpaperVideoUri: Uri? = null
    private var wallpaperPlayer: WallpaperPlayer? = null

    private fun wpPrefs() = getSharedPreferences("mooread", MODE_PRIVATE)

    private val takePic = registerForActivityResult(ActivityResultContracts.TakePicturePreview()) { bmp ->
        if (bmp == null) return@registerForActivityResult
        setActivity("OCR on camera still…", busy = true)
        Thread {
            val text = try { ocr.recognizeBitmap(bmp) } catch (ex: Exception) { ex.message ?: "" }
            runOnUiThread { acceptCameraText(text) }
        }.start()
    }

    private val openDoc = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) ingest(uri)
    }
    private val openFont = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) importFont(uri)
    }
    private val openWallpaper = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) setWallpaper(uri)
    }
    private val openVoice = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) importVoice(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)
        setContentView(R.layout.activity_main)
        readerView = findViewById(R.id.readerView)
        titleView = findViewById(R.id.titleView)
        nowPlaying = findViewById(R.id.nowPlaying)
        pipeView = findViewById(R.id.pipeView)
        playBtn = findViewById(R.id.playBtn)
        activityView = findViewById(R.id.activityView)
        busyBar = findViewById(R.id.busyBar)
        val splash = findViewById<View>(R.id.splash)
        val splashStatus = findViewById<TextView>(R.id.splashStatus)
        val playerBar = findViewById<LinearLayout>(R.id.playerBar)
        ViewCompat.setOnApplyWindowInsetsListener(playerBar) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(view.paddingLeft, view.paddingTop, view.paddingRight, bars.bottom + dp(28))
            insets
        }
        pipeline = TtsPipeline(this).also { engine ->
            engine.onStartChunk = { idx, text ->
                runOnUiThread {
                    nowPlaying.text = text
                    highlight(text)
                    setActivity("Speaking block ${idx + 1} — synthesizing next in background")
                    startBackgroundPlay(text)
                }
            }
            engine.onStatus = { msg ->
                runOnUiThread {
                    pipeView.text = msg
                    setActivity(msg)
                }
            }
            engine.onDoneAll = {
                runOnUiThread {
                    playing = false
                    playBtn.text = "Play"
                    nowPlaying.text = "Finished"
                    setActivity("Finished — buffers discarded", busy = false)
                    stopBackgroundPlay()
                }
            }
        }
        thread {
            val status = pipeline.initEngine()
            runOnUiThread {
                pipeView.text = status
                splashStatus.text = status
                splash.animate().alpha(0f).setDuration(280).withEndAction {
                    splash.visibility = View.GONE
                    maybeFirstRun()
                }.start()
            }
        }

        findViewById<Button>(R.id.openBtn).setOnClickListener {
            openDoc.launch(arrayOf(
                "application/epub+zip",
                "application/pdf",
                "text/plain",
                "text/rtf",
                "application/rtf",
                "image/*",
                "*/*"
            ))
        }
        findViewById<Button>(R.id.voiceBtn).setOnClickListener { pickProfile() }
        findViewById<Button>(R.id.menuBtn).setOnClickListener { showMenu() }
        findViewById<Button>(R.id.ltrBtn).setOnClickListener {
            ltrMode = !ltrMode
            val btn = findViewById<Button>(R.id.ltrBtn)
            btn.text = if (ltrMode) "LTR ON" else "RTL"
            readerView.textDirection = if (ltrMode) View.TEXT_DIRECTION_LTR else View.TEXT_DIRECTION_RTL
            readerView.textAlignment = if (ltrMode) View.TEXT_ALIGNMENT_TEXT_START else View.TEXT_ALIGNMENT_TEXT_END
            applyReadingOrder(resetCursor = true)
        }
        findViewById<Button>(R.id.cameraBtn).setOnClickListener { openCamera() }
        playBtn.setOnClickListener { togglePlay() }
        findViewById<Button>(R.id.stopBtn).setOnClickListener {
            pipeline.stop()
            playing = false
            playBtn.text = "Play"
            nowPlaying.text = "Stopped"
            setActivity("Stopped", busy = false)
            stopBackgroundPlay()
        }
        findViewById<Button>(R.id.nextBtn).setOnClickListener { pipeline.next() }
        findViewById<Button>(R.id.prevBtn).setOnClickListener { pipeline.prev() }
        findViewById<Button>(R.id.loopBtn).setOnClickListener {
            pipeline.looping = !pipeline.looping
            val btn = findViewById<Button>(R.id.loopBtn)
            btn.text = if (pipeline.looping) "Loop ON" else "Loop"
            btn.isSelected = pipeline.looping
            setActivity(if (pipeline.looping) "Loop on — will replay the whole file" else "Loop off", busy = false)
        }
        applyStoredColors()
        bindWallpaperTilt()
        applyWallpaper()
        val existingFont = File(filesDir, "custom-font.bin")
        if (existingFont.exists() && existingFont.length() > 0) {
            try {
                val tf = android.graphics.Typeface.createFromFile(existingFont)
                readerView.typeface = tf
                titleView.typeface = tf
            } catch (_: Exception) {}
        }
        intent?.data?.let { ingest(it) }
    }

    private fun looksPdf(uri: Uri): Boolean {
        return try {
            contentResolver.openInputStream(uri)?.use { ins ->
                val magic = ByteArray(5)
                val n = ins.read(magic)
                n >= 4 && magic[0] == '%'.code.toByte() && magic[1] == 'P'.code.toByte() &&
                    magic[2] == 'D'.code.toByte() && magic[3] == 'F'.code.toByte()
            } ?: false
        } catch (_: Exception) {
            false
        }
    }

    private fun ingest(uri: Uri) {
        try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
        }
        Thread {
            try {
                runOnUiThread { setActivity("Opening file — first readable page only…", busy = true) }
                val name = uri.lastPathSegment?.lowercase() ?: ""
                val mime = (contentResolver.getType(uri) ?: "").lowercase()
                val isPdf = name.contains(".pdf") || mime.contains("pdf") || looksPdf(uri)
                speech?.close()
                val source = SpeechSource(ocr)
                speech = source
                source.onStatus = { msg -> runOnUiThread { setActivity(msg, busy = true) } }
                source.onGrow = { text ->
                    runOnUiThread {
                        val scroll = findViewById<android.widget.ScrollView>(R.id.scroll)
                        val y = scroll.scrollY
                        readerView.text = text
                        scroll.post { scroll.scrollTo(0, y) }
                    }
                }
                if (isPdf) {
                    source.openUri(this, uri, null, true)
                } else {
                    val loaded = DocumentLoader.load(this, uri, ocr) { msg ->
                        runOnUiThread { setActivity(msg, busy = true) }
                    }
                    source.openText(loaded.title, loaded.text, loaded.kind)
                }
                val ready = source.snapshot()
                runOnUiThread {
                    doc = LoadedDoc(source.title, source.displayText(), source.kind, ready)
                    titleView.text = source.title
                    readerView.text = source.displayText().ifBlank { "Scanning for readable text…" }
                    applyReadingOrder(resetCursor = true)
                    if (ready.isEmpty()) {
                        nowPlaying.text = "No speakable text yet"
                        setActivity("No readable words on the first pages. Play will keep scanning.", busy = false)
                    } else {
                        nowPlaying.text = "${ready.size} block(s) ready — more pages OCR as you listen"
                        setActivity("Ready — ${ready.size} block(s). Press Play. Later pages load while speaking.", busy = false)
                    }
                }
            } catch (ex: Exception) {
                runOnUiThread {
                    setActivity("Load failed: ${ex.message}", busy = false)
                    Toast.makeText(this, ex.message, Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    private fun importVoice(uri: Uri) {
        try {
            val dest = File(filesDir, "voice-${System.currentTimeMillis()}.json")
            contentResolver.openInputStream(uri)?.use { input ->
                FileOutputStream(dest).use { input.copyTo(it) }
            }
            val profile = VoiceProfiles.loadFile(dest)
            profiles.add(0, profile)
            currentProfile = profile
            applyReadingOrder(resetCursor = true)
            Toast.makeText(this, "Loaded voice ${profile.name}", Toast.LENGTH_SHORT).show()
        } catch (ex: Exception) {
            Toast.makeText(this, "Voice profile error: ${ex.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun pickProfile() {
        val names = profiles.map { it.name }.toTypedArray() + "Import profile file…"
        AlertDialog.Builder(this)
            .setTitle("Voice profile")
            .setItems(names) { _, which ->
                if (which == names.lastIndex) {
                    openVoice.launch(arrayOf("application/json", "text/*", "*/*"))
                } else {
                    currentProfile = profiles[which]
                    applyReadingOrder(resetCursor = true)
                }
            }
            .show()
    }

    private fun orderedChunks(chunks: List<String>): List<String> {
        return if (ltrMode) chunks else chunks.asReversed()
    }

    private fun applyReadingOrder(resetCursor: Boolean) {
        val source = speech
        val fromSource = source?.snapshot().orEmpty()
        val loaded = doc
        val chunks = when {
            fromSource.isNotEmpty() -> if (ltrMode) fromSource else fromSource.asReversed()
            loaded != null -> orderedChunks(loaded.chunks)
            !source?.displayText().isNullOrBlank() -> DocumentLoader.chunk(source!!.displayText())
            else -> emptyList()
        }
        if (chunks.isEmpty()) {
            if (source != null) {
                pipeline.loadSource(source, currentProfile, if (resetCursor) 0 else pipeline.currentIndex)
                setActivity("Scanning for readable words. Play will start when a page has text.", busy = false)
            } else {
                setActivity("Nothing speakable loaded yet", busy = false)
            }
            return
        }
        pipeline.load(chunks, currentProfile, if (resetCursor) 0 else pipeline.currentIndex)
        pipeline.source = source
        readerView.text = source?.displayText()?.ifBlank { chunks.joinToString("\n\n") } ?: chunks.joinToString("\n\n")
        setActivity("Voice queue ${chunks.size} block(s). Press Play.", busy = false)
    }

    private fun acceptCameraText(raw: String) {
        val text = raw.trim().ifBlank { "" }
        if (text.isEmpty()) {
            readerView.text = "[No text in photo]"
            setActivity("No readable text in that shot", busy = false)
            Toast.makeText(this, "No text found — try closer / more light", Toast.LENGTH_LONG).show()
            return
        }
        val loaded = DocumentLoader.fromText("Camera", text, "camera")
        speech?.close()
        speech = SpeechSource(ocr).also { it.openText("Camera", text, "camera") }
        doc = loaded
        titleView.text = "Camera"
        readerView.text = loaded.text
        applyReadingOrder(resetCursor = true)
        nowPlaying.text = "${loaded.chunks.size} blocks ready"
        setActivity("Camera page ready — ${loaded.chunks.size} blocks. Press Play.", busy = false)
    }

    private fun togglePlay() {
        if (doc == null) {
            val onScreen = readerView.text.toString().trim()
            if (onScreen.isNotEmpty() && !onScreen.startsWith("Open an EPUB")) {
                acceptCameraText(onScreen)
            }
        }
        val loaded = doc
        val canPlay = pipeline.hasWork() || (loaded != null && loaded.chunks.isNotEmpty()) || (speech?.knownCount() ?: 0) > 0 || speech != null
        if (!canPlay) {
            Toast.makeText(this, "Open a file or take a picture first", Toast.LENGTH_SHORT).show()
            return
        }
        if (!playing) {
            if (pipeline.chunks.isEmpty()) applyReadingOrder(resetCursor = pipeline.currentIndex == 0)
            setActivity("Starting Kokoro — first block may take a few seconds…", busy = true)
            pipeline.play()
            playing = true
            playBtn.text = "Pause"
            startBackgroundPlay(loaded?.title ?: speech?.title ?: "MooRead")
        } else {
            pipeline.pause()
            playing = false
            playBtn.text = "Play"
            setActivity("Paused", busy = false)
            stopBackgroundPlay()
        }
    }

    private fun highlight(snippet: String) {
        // Keep the user's scroll position. Jumping to every phrase felt spasmodic.
    }

    private fun showMenu() {
        val items = arrayOf(
            "Color theming",
            "Themes…",
            "Browse font",
            "Background…",
            if (translateOn) "Translate JA→EN: ON" else "Translate JA→EN: OFF",
            "Reset settings",
            "Exit MooRead"
        )
        AlertDialog.Builder(this)
            .setTitle("Menu")
            .setItems(items) { _, which ->
                when (which) {
                    0 -> showThemeDialog()
                    1 -> showThemesGallery()
                    2 -> openFont.launch(arrayOf("font/ttf", "font/otf", "application/font-sfnt", "*/*"))
                    3 -> showBackgroundMenu()
                    4 -> {
                        translateOn = !translateOn
                        Toast.makeText(this, if (translateOn) "JA→EN on" else "JA→EN off", Toast.LENGTH_SHORT).show()
                    }
                    5 -> resetToDefaults()
                    6 -> {
                        stopBackgroundPlay()
                        pipeline.stop()
                        finishAndRemoveTask()
                    }
                }
            }
            .show()
    }

    private fun showWallpaperFitMenu() {
        val modes = arrayOf("Stretch", "Contain", "Cover", "Center")
        AlertDialog.Builder(this)
            .setTitle("Wallpaper fit")
            .setItems(modes) { _, which ->
                val name = when (which) {
                    0 -> "stretch"
                    1 -> "contain"
                    2 -> "cover"
                    else -> "center"
                }
                wpPrefs().edit().putString("wallpaper_fit", name).commit()
                applyWallpaperFit()
            }
            .show()
    }

    private fun setWallpaper(uri: Uri) {
        try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
        }
        val type = (contentResolver.getType(uri) ?: "").lowercase()
        val path = uri.toString().lowercase()
        val name = (uri.lastPathSegment ?: "").lowercase()
        val looksPack = name.endsWith(".pkg") || name.endsWith(".mpkg") || name.endsWith("project.json")
        if (looksPack) {
            thread {
                val file = try { WallpaperPack.import(this, uri) } catch (_: Exception) { null }
                runOnUiThread {
                    if (file == null) {
                        Toast.makeText(this, "Could not unpack Wallpaper Engine file", Toast.LENGTH_LONG).show()
                    } else {
                        val local = Uri.fromFile(file)
                        val video = file.extension.lowercase() in setOf("mp4", "webm", "mkv", "mov", "avi")
                        wpPrefs().edit()
                            .putString("wallpaper_uri", local.toString())
                            .putBoolean("wallpaper_is_video", video)
                            .commit()
                        applyWallpaper()
                        Toast.makeText(this, if (video) "WE video wallpaper — looping" else "Wallpaper Engine preview set", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            return
        }
        val isVideo = type.startsWith("video") ||
            path.endsWith(".mp4") || path.endsWith(".webm") || path.endsWith(".mkv") ||
            path.endsWith(".mov") || path.endsWith(".avi")
        wpPrefs().edit()
            .putString("wallpaper_uri", uri.toString())
            .putBoolean("wallpaper_is_video", isVideo)
            .commit()
        applyWallpaper()
        Toast.makeText(
            this,
            if (isVideo) "Video wallpaper — loops until you change it" else "Wallpaper set",
            Toast.LENGTH_SHORT
        ).show()
    }

    private fun applyWallpaper() {
        val image = findViewById<ImageView>(R.id.wallpaperView)
        val video = findViewById<TextureView>(R.id.wallpaperVideo)
        if (wallpaperPlayer == null) wallpaperPlayer = WallpaperPlayer(video)
        val prefs = wpPrefs()
        val opacity = prefs.getFloat("wallpaper_opacity", 0.35f).coerceIn(0.05f, 1f)
        image.alpha = opacity
        video.alpha = opacity
        applyWallpaperFit()
        val uriStr = prefs.getString("wallpaper_uri", "") ?: ""
        val isVideo = prefs.getBoolean("wallpaper_is_video", false)
        val muted = prefs.getBoolean("wallpaper_muted", true)
        if (uriStr.isBlank()) {
            wallpaperPlayer?.stop()
            wallpaperVideoUri = null
            image.setImageDrawable(null)
            image.visibility = View.VISIBLE
            return
        }
        val uri = Uri.parse(uriStr)
        if (isVideo) {
            image.setImageDrawable(null)
            image.visibility = View.INVISIBLE
            wallpaperVideoUri = uri
            wallpaperPlayer?.play(uri, muted)
        } else {
            wallpaperPlayer?.stop()
            wallpaperVideoUri = null
            image.visibility = View.VISIBLE
            image.setImageURI(uri)
        }
        bindWallpaperTilt()
    }

    private fun applyWallpaperFit() {
        val image = findViewById<ImageView>(R.id.wallpaperView)
        image.scaleType = when (wpPrefs().getString("wallpaper_fit", "cover")) {
            "stretch" -> ImageView.ScaleType.FIT_XY
            "contain" -> ImageView.ScaleType.FIT_CENTER
            "center" -> ImageView.ScaleType.CENTER
            else -> ImageView.ScaleType.CENTER_CROP
        }
    }

    private fun bindWallpaperTilt() {
        val image = findViewById<ImageView>(R.id.wallpaperView)
        val video = findViewById<TextureView>(R.id.wallpaperVideo)
        if (wallpaperTilt == null) {
            wallpaperTilt = WallpaperTilt(this, listOf(image, video))
        }
        val prefs = wpPrefs()
        val tilt = wallpaperTilt ?: return
        tilt.aggressiveness = prefs.getFloat("wallpaper_tilt_agg", 0.45f)
        if (prefs.getBoolean("wallpaper_tilt", false)) tilt.start() else tilt.stop()
    }

    private fun showBackgroundMenu() {
        val prefs = wpPrefs()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(8))
        }
        box.addView(TextView(this).apply {
            text = "Backgrounds sit behind the book. Video files loop here; the player Loop button only repeats speech."
            setTextColor(0xFFC5D6C4.toInt())
            textSize = 13f
            setPadding(0, 0, 0, dp(8))
        })
        box.addView(Button(this).apply {
            text = "Choose image or video…"
            setOnClickListener { openWallpaper.launch(arrayOf("image/*", "video/*", "*/*")) }
        })
        box.addView(Button(this).apply {
            text = "Import Wallpaper Engine file…"
            setOnClickListener { openWallpaper.launch(arrayOf("*/*")) }
        })
        box.addView(Button(this).apply {
            text = "Fit…"
            setOnClickListener { showWallpaperFitMenu() }
        })
        box.addView(Button(this).apply {
            text = "Clear background"
            setOnClickListener {
                prefs.edit().putString("wallpaper_uri", "").putBoolean("wallpaper_is_video", false).commit()
                applyWallpaper()
                Toast.makeText(this@MainActivity, "Background cleared", Toast.LENGTH_SHORT).show()
            }
        })
        val mute = CheckBox(this).apply {
            text = "Mute wallpaper audio"
            isChecked = prefs.getBoolean("wallpaper_muted", true)
            setTextColor(0xFFE8EDF2.toInt())
            setOnCheckedChangeListener { _, on ->
                prefs.edit().putBoolean("wallpaper_muted", on).commit()
                wallpaperPlayer?.setMuted(on)
            }
        }
        box.addView(mute)
        val tiltBox = CheckBox(this).apply {
            text = "Gyro tilt parallax"
            isChecked = prefs.getBoolean("wallpaper_tilt", false)
            setTextColor(0xFFE8EDF2.toInt())
        }
        box.addView(tiltBox)
        box.addView(TextView(this).apply {
            text = "Tilt aggressiveness"
            setTextColor(0xFFE8EDF2.toInt())
            setPadding(0, dp(8), 0, 0)
        })
        val agg = SeekBar(this).apply {
            max = 100
            progress = (prefs.getFloat("wallpaper_tilt_agg", 0.45f) * 100f).toInt().coerceIn(0, 100)
        }
        val aggLabel = TextView(this).apply {
            text = "${agg.progress}%"
            setTextColor(0xFFC5D6C4.toInt())
        }
        agg.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                aggLabel.text = "$progress%"
                prefs.edit().putFloat("wallpaper_tilt_agg", progress / 100f).commit()
                wallpaperTilt?.aggressiveness = progress / 100f
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })
        box.addView(agg)
        box.addView(aggLabel)

        val alpha = prefs.getFloat("wallpaper_opacity", 0.35f).coerceIn(0.05f, 1f)
        val startTrans = ((1f - alpha) * 100f).toInt().coerceIn(0, 95)
        val transLabel = TextView(this).apply {
            text = if (startTrans == 0) "Translucency 0% — fully opaque" else "Translucency $startTrans%"
            setTextColor(0xFFE8EDF2.toInt())
            setPadding(0, dp(10), 0, 0)
        }
        box.addView(transLabel)
        val trans = SeekBar(this).apply {
            max = 95
            progress = startTrans
        }
        trans.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val translucency = progress.coerceIn(0, 95)
                val value = 1f - translucency / 100f
                transLabel.text = if (translucency == 0) "Translucency 0% — fully opaque" else "Translucency $translucency%"
                prefs.edit().putFloat("wallpaper_opacity", value).commit()
                findViewById<ImageView>(R.id.wallpaperView).alpha = value
                findViewById<TextureView>(R.id.wallpaperVideo).alpha = value
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })
        box.addView(trans)
        box.addView(TextView(this).apply {
            text = "0% = 100% opaque background. 95% = almost see-through."
            setTextColor(0xFF9AA7B2.toInt())
            textSize = 12f
        })
        tiltBox.setOnCheckedChangeListener { _, on ->
            prefs.edit().putBoolean("wallpaper_tilt", on).commit()
            bindWallpaperTilt()
        }
        AlertDialog.Builder(this)
            .setTitle("Background")
            .setView(box)
            .setPositiveButton("Close", null)
            .show()
    }

    private fun openCamera() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), 77)
            Toast.makeText(this, "Allow camera, then tap Camera again", Toast.LENGTH_SHORT).show()
            return
        }
        try {
            takePic.launch(null)
        } catch (ex: Exception) {
            Toast.makeText(this, "Camera unavailable: ${ex.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun showThemesGallery() {
        val root = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(dp(12), dp(8), dp(12), dp(8))
        }
        val list = android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.VERTICAL }
        val selected = mutableSetOf<String>()
        fun hex(s: String, fallback: String) = try { android.graphics.Color.parseColor(s) } catch (_: Exception) { android.graphics.Color.parseColor(fallback) }
        fun applyTheme(t: VisualTheme) {
            val clearFx = t.fx == "none" || t.id == "normal"
            val ed = getSharedPreferences("mooread", MODE_PRIVATE).edit()
                .putString("app_color", t.appColor)
                .putString("button_color", t.buttonColor)
                .putString("reader_color", t.readerColor)
                .putString("outline_color", t.outlineColor)
                .putString("theme_id", if (clearFx) "" else t.id)
                .putString("theme_fx", if (clearFx) "none" else t.fx)
            ed.commit()
            applyStoredColors()
            Toast.makeText(this, "Loaded ${t.name}", Toast.LENGTH_SHORT).show()
        }
        fun paintList() {
            list.removeAllViews()
            selected.clear()
            ThemeStore.all(this).forEach { theme ->
                val card = android.widget.LinearLayout(this).apply {
                    orientation = android.widget.LinearLayout.VERTICAL
                    setPadding(dp(10), dp(10), dp(10), dp(10))
                    setBackgroundColor(hex(theme.appColor, "#121417"))
                }
                val thumb = TextView(this).apply {
                    text = "MOOREAD\nAa  雨  本文"
                    textSize = 16f
                    setTypeface(typeface, android.graphics.Typeface.BOLD)
                    setTextColor(hex(theme.readerColor, "#E8EDF2"))
                    setPadding(dp(8), dp(12), dp(8), dp(12))
                    setShadowLayer(2f, 1f, 1f, hex(theme.outlineColor, "#000000"))
                }
                val meta = TextView(this).apply {
                    text = theme.name + if (theme.locked) "  ·  locked" else "  ·  custom"
                    setTextColor(hex(theme.buttonColor, "#F3F7EF"))
                    textSize = 14f
                }
                val blurb = TextView(this).apply {
                    text = theme.blurb
                    setTextColor(hex(theme.buttonColor, "#F3F7EF"))
                    textSize = 12f
                    alpha = 0.8f
                }
                val load = Button(this).apply {
                    text = "Load"
                    setOnClickListener { applyTheme(theme) }
                }
                card.addView(thumb)
                card.addView(meta)
                card.addView(blurb)
                card.addView(load)
                if (!theme.locked) {
                    val box = android.widget.CheckBox(this).apply {
                        text = "Select"
                        setTextColor(hex(theme.buttonColor, "#F3F7EF"))
                        setOnCheckedChangeListener { _, on ->
                            if (on) selected += theme.id else selected -= theme.id
                        }
                    }
                    card.addView(box)
                }
                val pad = android.widget.LinearLayout(this).apply {
                    orientation = android.widget.LinearLayout.VERTICAL
                    setPadding(0, 0, 0, dp(10))
                    addView(card)
                }
                list.addView(pad)
            }
        }
        val saveRow = android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.HORIZONTAL }
        val name = android.widget.EditText(this).apply {
            hint = "Name this look"
            setTextColor(0xFFE8EDF2.toInt())
            setHintTextColor(0xFF9AA7B2.toInt())
            layoutParams = android.widget.LinearLayout.LayoutParams(0, android.widget.LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        val save = Button(this).apply {
            text = "Save"
            setOnClickListener {
                val prefs = getSharedPreferences("mooread", MODE_PRIVATE)
                try {
                    ThemeStore.save(
                        this@MainActivity,
                        name.text.toString(),
                        prefs.getString("app_color", "#121417") ?: "#121417",
                        prefs.getString("button_color", "#F3F7EF") ?: "#F3F7EF",
                        prefs.getString("reader_color", "#E8EDF2") ?: "#E8EDF2",
                        prefs.getString("outline_color", "#000000") ?: "#000000"
                    )
                    paintList()
                    Toast.makeText(this@MainActivity, "Theme saved", Toast.LENGTH_SHORT).show()
                } catch (ex: Exception) {
                    Toast.makeText(this@MainActivity, ex.message, Toast.LENGTH_LONG).show()
                }
            }
        }
        saveRow.addView(name)
        saveRow.addView(save)
        val del = Button(this).apply {
            text = "Delete selected"
            setOnClickListener {
                val n = ThemeStore.delete(this@MainActivity, selected.toList())
                paintList()
                Toast.makeText(this@MainActivity, "Deleted $n custom theme(s)", Toast.LENGTH_SHORT).show()
            }
        }
        val unload = Button(this).apply {
            text = "Unload theme — default look"
            setOnClickListener {
                unloadShaderTheme()
                applyWallpaper()
                Toast.makeText(this@MainActivity, "Default look, no shader", Toast.LENGTH_SHORT).show()
            }
        }
        root.addView(saveRow)
        root.addView(unload)
        root.addView(del)
        root.addView(android.widget.ScrollView(this).apply {
            addView(list)
            layoutParams = android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT, dp(420)
            )
        })
        paintList()
        AlertDialog.Builder(this)
            .setTitle("Themes")
            .setView(root)
            .setNegativeButton("Close", null)
            .show()
    }

    private fun showThemeDialog() {
        val prefs = getSharedPreferences("mooread", MODE_PRIVATE)
        val keys = arrayOf(
            "app_color" to "App UI",
            "button_color" to "Button / UI text",
            "reader_color" to "Book text",
            "outline_color" to "Text outline"
        )
        val defaults = mapOf(
            "app_color" to "#121417",
            "button_color" to "#F3F7EF",
            "reader_color" to "#E8EDF2",
            "outline_color" to "#000000"
        )
        val container = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(8))
        }
        data class Row(val key: String, val sliders: Array<android.widget.SeekBar>, val hex: android.widget.EditText)
        val rows = mutableListOf<Row>()
        themeSnap = mapOf(
            "app_color" to (prefs.getString("app_color", "#121417") ?: "#121417"),
            "button_color" to (prefs.getString("button_color", "#F3F7EF") ?: "#F3F7EF"),
            "reader_color" to (prefs.getString("reader_color", "#E8EDF2") ?: "#E8EDF2"),
            "outline_color" to (prefs.getString("outline_color", "#000000") ?: "#000000"),
            "theme_id" to (prefs.getString("theme_id", "") ?: ""),
            "theme_fx" to (prefs.getString("theme_fx", "") ?: "")
        )
        val previewChrome = TextView(this).apply { text = "MooRead preview"; setPadding(dp(8), dp(8), dp(8), dp(4)); textSize = 16f }
        val previewBtn = TextView(this).apply { text = "Play button text"; setPadding(dp(8), 0, dp(8), dp(4)) }
        val previewRead = TextView(this).apply { text = "The rain kept a soft count on the roof."; setPadding(dp(8), 0, dp(8), dp(12)); textSize = 16f }
        container.addView(previewChrome)
        container.addView(previewBtn)
        container.addView(previewRead)
        fun paintPreview() {
            fun col(i: Int, fallback: String): Int = try {
                android.graphics.Color.parseColor(rows.getOrNull(i)?.hex?.text?.toString() ?: fallback)
            } catch (_: Exception) { android.graphics.Color.parseColor(fallback) }
            val app = col(0, "#121417")
            val button = col(1, "#F3F7EF")
            val read = col(2, "#E8EDF2")
            container.setBackgroundColor(app)
            previewChrome.setTextColor(read)
            previewBtn.setTextColor(button)
            previewRead.setTextColor(read)
            findViewById<View>(R.id.root).setBackgroundColor(app)
            readerView.setTextColor(read)
            titleView.setTextColor(read)
            listOf(R.id.openBtn, R.id.voiceBtn, R.id.menuBtn, R.id.prevBtn, R.id.playBtn, R.id.stopBtn, R.id.nextBtn, R.id.loopBtn).forEach { id ->
                findViewById<Button>(id).setTextColor(button)
            }
        }
        keys.forEach { (key, label) ->
            val start = try { android.graphics.Color.parseColor(prefs.getString(key, defaults[key])) } catch (_: Exception) { android.graphics.Color.BLACK }
            container.addView(TextView(this).apply { text = label; setTextColor(0xFFE8EDF2.toInt()); textSize = 16f })
            val sliders = Array(3) { android.widget.SeekBar(this) }
            sliders[0].progress = android.graphics.Color.red(start)
            sliders[1].progress = android.graphics.Color.green(start)
            sliders[2].progress = android.graphics.Color.blue(start)
            sliders.forEach { it.max = 255 }
            val hex = android.widget.EditText(this).apply {
                setText("#%06X".format(0xFFFFFF and start))
                setTextColor(0xFFE8EDF2.toInt())
            }
            sliders.forEachIndexed { i, bar ->
                container.addView(TextView(this).apply { text = arrayOf("R", "G", "B")[i]; setTextColor(0xFF9AA7B2.toInt()) })
                container.addView(bar)
                bar.setOnSeekBarChangeListener(object : android.widget.SeekBar.OnSeekBarChangeListener {
                    override fun onProgressChanged(s: android.widget.SeekBar?, p: Int, u: Boolean) {
                        hex.setText("#%06X".format(0xFFFFFF and android.graphics.Color.rgb(sliders[0].progress, sliders[1].progress, sliders[2].progress)))
                        paintPreview()
                    }
                    override fun onStartTrackingTouch(s: android.widget.SeekBar?) {}
                    override fun onStopTrackingTouch(s: android.widget.SeekBar?) {}
                })
            }
            container.addView(hex)
            rows += Row(key, sliders, hex)
        }
        paintPreview()
        val scroll = android.widget.ScrollView(this).apply { addView(container) }
        AlertDialog.Builder(this)
            .setTitle("Color theming")
            .setView(scroll)
            .setPositiveButton("Apply") { _, _ ->
                val ed = prefs.edit()
                rows.forEach { row ->
                    val typed = row.hex.text.toString().trim()
                    ed.putString(row.key, if (typed.startsWith("#") && typed.length == 7) typed else "#%06X".format(0xFFFFFF and android.graphics.Color.rgb(row.sliders[0].progress, row.sliders[1].progress, row.sliders[2].progress)))
                }
                ed.apply()
                applyStoredColors()
            }
            .setNegativeButton("Cancel") { _, _ ->
                prefs.edit()
                    .putString("app_color", themeSnap["app_color"])
                    .putString("button_color", themeSnap["button_color"])
                    .putString("reader_color", themeSnap["reader_color"])
                    .putString("outline_color", themeSnap["outline_color"])
                    .putString("theme_id", themeSnap["theme_id"])
                    .putString("theme_fx", themeSnap["theme_fx"])
                    .apply()
                applyStoredColors()
            }
            .show()
    }

    private fun importFont(uri: Uri) {
        try {
            val dest = File(filesDir, "custom-font.bin")
            contentResolver.openInputStream(uri)?.use { input ->
                FileOutputStream(dest).use { input.copyTo(it) }
            }
            readerView.typeface = android.graphics.Typeface.createFromFile(dest)
            titleView.typeface = android.graphics.Typeface.createFromFile(dest)
            Toast.makeText(this, "Custom font loaded", Toast.LENGTH_SHORT).show()
        } catch (ex: Exception) {
            Toast.makeText(this, "Font error: ${ex.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun themedButtons(): List<Button> = listOf(
        R.id.ltrBtn, R.id.cameraBtn, R.id.openBtn, R.id.voiceBtn, R.id.menuBtn,
        R.id.prevBtn, R.id.playBtn, R.id.stopBtn, R.id.nextBtn, R.id.loopBtn
    ).map { findViewById(it) }

    private fun writeDefaultLook(editor: android.content.SharedPreferences.Editor): android.content.SharedPreferences.Editor {
        return editor
            .putString("app_color", "#121417")
            .putString("button_color", "#F3F7EF")
            .putString("reader_color", "#E8EDF2")
            .putString("outline_color", "#000000")
            .putString("theme_id", "")
            .putString("theme_fx", "none")
            .putString("wallpaper_uri", "")
            .putBoolean("wallpaper_is_video", false)
            .putBoolean("wallpaper_tilt", false)
            .putFloat("wallpaper_tilt_agg", 0.45f)
            .putFloat("wallpaper_opacity", 0.35f)
            .putBoolean("wallpaper_muted", true)
            .putString("wallpaper_fit", "cover")
    }

    private fun unloadShaderTheme() {
        writeDefaultLook(getSharedPreferences("mooread", MODE_PRIVATE).edit()).commit()
        applyStoredColors()
        applyWallpaper()
    }

    private fun resetToDefaults() {
        val prefs = getSharedPreferences("mooread", MODE_PRIVATE)
        writeDefaultLook(prefs.edit().clear()).commit()
        AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)
        wallpaperPlayer?.stop()
        wallpaperTilt?.stop()
        applyStoredColors()
        applyWallpaper()
        Toast.makeText(this, "Reset to dark mode defaults (no shader)", Toast.LENGTH_SHORT).show()
    }

    private fun applyStoredColors() {
        val prefs = getSharedPreferences("mooread", MODE_PRIVATE)
        fun parse(key: String, fallback: String): Int = try {
            android.graphics.Color.parseColor(prefs.getString(key, fallback))
        } catch (_: Exception) { android.graphics.Color.parseColor(fallback) }
        findViewById<View>(R.id.root).setBackgroundColor(parse("app_color", "#121417"))
        findViewById<View>(R.id.contentRoot).setBackgroundColor(parse("app_color", "#121417"))
        readerView.setTextColor(parse("reader_color", "#E8EDF2"))
        titleView.setTextColor(parse("reader_color", "#E8EDF2"))
        nowPlaying.setTextColor(parse("reader_color", "#E8EDF2"))
        pipeView.setTextColor(parse("button_color", "#F3F7EF"))
        activityView.setTextColor(parse("button_color", "#F3F7EF"))
        findViewById<TextView>(R.id.brandView).setTextColor(parse("reader_color", "#E8EDF2"))
        (readerView as OutlineTextView).strokeColor = parse("outline_color", "#000000")
        val btn = parse("button_color", "#F3F7EF")
        themedButtons().forEach { it.setTextColor(btn) }
        findViewById<View>(R.id.playerBar).setBackgroundColor(
            ThemeFx.playerColor(prefs.getString("theme_fx", prefs.getString("theme_id", "")) ?: "")
        )
        findViewById<android.widget.ImageView>(R.id.wallpaperView).colorFilter = null
        if (themeFx == null) {
            themeFx = ThemeFxController(findViewById(R.id.contentRoot))
        }
        val fx = ThemeFx.normalize(prefs.getString("theme_id", ""), prefs.getString("theme_fx", ""))
        themeFx?.apply(
            fx,
            findViewById(R.id.wallpaperView),
            themedButtons(),
            listOf(readerView, titleView, nowPlaying, pipeView, activityView, findViewById(R.id.brandView))
        )
    }

    private fun setActivity(msg: String, busy: Boolean = true) {
        activityView.text = msg
        busyBar.visibility = if (busy) View.VISIBLE else View.GONE
    }

    private fun startBackgroundPlay(text: String) {
        val i = Intent(this, PlaybackService::class.java)
            .putExtra(PlaybackService.EXTRA_TITLE, "MooRead")
            .putExtra(PlaybackService.EXTRA_TEXT, text.take(80))
        if (android.os.Build.VERSION.SDK_INT >= 26) startForegroundService(i) else startService(i)
    }

    private fun stopBackgroundPlay() {
        stopService(Intent(this, PlaybackService::class.java))
    }

    private fun maybeFirstRun() {
        val prefs = getSharedPreferences("mooread", MODE_PRIVATE)
        if (prefs.getBoolean("first_run_done", false)) return
        AlertDialog.Builder(this)
            .setTitle("MooRead")
            .setMessage("For your sanity this application defaults to darkmode and 3% volume on first run, however on subsequent runs it will retain your settings unless you press reset.")
            .setPositiveButton("OK") { _, _ -> prefs.edit().putBoolean("first_run_done", true).apply() }
            .setCancelable(false)
            .show()
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    override fun onResume() {
        super.onResume()
        bindWallpaperTilt()
        if (wpPrefs().getBoolean("wallpaper_is_video", false) && wallpaperPlayer == null) {
            applyWallpaper()
        }
    }

    override fun onPause() {
        wallpaperTilt?.stop()
        super.onPause()
    }

    override fun onDestroy() {
        wallpaperPlayer?.stop()
        wallpaperTilt?.stop()
        speech?.close()
        pipeline.shutdown()
        super.onDestroy()
    }
}
