package com.mooread.app

import org.json.JSONObject
import java.io.File

data class VoiceStyle(
    val rate: Float = 1.0f,
    val pitch: Float = 1.0f,
    val emotionBias: String = "neutral",
    val diction: String = "narrative"
)

data class VoiceProfile(
    val id: String,
    val name: String,
    val androidVoice: String = "",
    val kokoroVoice: String = "af_bella",
    val locale: String = "en-US",
    val style: VoiceStyle = VoiceStyle(),
    val lexicon: Map<String, String> = emptyMap()
)

object VoiceProfiles {
    fun builtin(): List<VoiceProfile> = listOf(
        VoiceProfile("storyteller", "Bella — storyteller", kokoroVoice = "af_bella"),
        VoiceProfile("documentary", "Nicole — documentary", kokoroVoice = "af_nicole", style = VoiceStyle(0.98f, 0.97f, "neutral", "documentary")),
        VoiceProfile("michael", "Michael — lecture", kokoroVoice = "am_michael", style = VoiceStyle(0.97f, 1.0f, "grave", "lecture")),
        VoiceProfile("george", "George — British", kokoroVoice = "bm_george", locale = "en-GB"),
        VoiceProfile("japanese", "Alpha — Japanese narrator", kokoroVoice = "jf_alpha", locale = "ja-JP")
    )

    fun loadFile(file: File): VoiceProfile {
        val json = JSONObject(file.readText())
        val styleObj = json.optJSONObject("style") ?: JSONObject()
        val lexObj = json.optJSONObject("lexicon") ?: JSONObject()
        val lex = mutableMapOf<String, String>()
        lexObj.keys().forEach { lex[it] = lexObj.getString(it) }
        return VoiceProfile(
            id = json.optString("id", file.nameWithoutExtension),
            name = json.optString("name", file.nameWithoutExtension),
            androidVoice = json.optString("android_voice"),
            kokoroVoice = json.optString("kokoro_voice", "af_bella"),
            locale = json.optString("locale", "en-US"),
            style = VoiceStyle(
                rate = styleObj.optDouble("rate", 1.0).toFloat(),
                pitch = styleObj.optDouble("pitch", 1.0).toFloat(),
                emotionBias = styleObj.optString("emotion_bias", "neutral"),
                diction = styleObj.optString("diction", "narrative")
            ),
            lexicon = lex
        )
    }

    fun applyLexicon(text: String, profile: VoiceProfile): String {
        var out = text
        for ((k, v) in profile.lexicon) {
            out = out.replace(Regex("\\b${Regex.escape(k)}\\b"), v)
        }
        return out
    }
}
