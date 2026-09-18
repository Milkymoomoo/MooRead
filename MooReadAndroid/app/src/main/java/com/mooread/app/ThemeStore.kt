package com.mooread.app

import android.content.Context
import org.json.JSONObject
import java.io.File

data class VisualTheme(
    val id: String,
    val name: String,
    val locked: Boolean,
    val blurb: String,
    val appColor: String,
    val buttonColor: String,
    val readerColor: String,
    val outlineColor: String,
    val fx: String = "none"
)

object ThemeStore {
    val builtins = listOf(
        VisualTheme("normal", "Normal", true, "Default dark UI · no shader", "#121417", "#F3F7EF", "#E8EDF2", "#000000", "none"),
        VisualTheme("amber-crt", "Amber CRT", true, "P3 amber phosphor · scanlines, bloom, flicker", "#140C04", "#FFC14A", "#FFB000", "#4A2200", "amber-crt"),
        VisualTheme("mac-platinum", "Macintosh Platinum", true, "System 7 greyscale · platinum chrome bevels", "#C0C0C0", "#000000", "#111111", "#FFFFFF", "mac-platinum"),
        VisualTheme("gameboy-dmg", "Game Boy DMG", true, "DMG-01 olive LCD · 4-color palette, pixel grid, ghosting", "#0F380F", "#9BBC0F", "#8BAC0F", "#306230", "gameboy-dmg")
    )

    private fun dir(context: Context) = File(context.filesDir, "themes").apply { mkdirs() }

    fun all(context: Context): List<VisualTheme> {
        val extra = dir(context).listFiles { f -> f.extension == "json" }?.mapNotNull { file ->
            try {
                val j = JSONObject(file.readText())
                val id = j.optString("id", file.nameWithoutExtension)
                if (builtins.any { it.id == id }) null
                else VisualTheme(
                    id = id,
                    name = j.optString("name", id),
                    locked = false,
                    blurb = j.optString("blurb", "Custom saved look"),
                    appColor = j.optString("app_color", "#121417"),
                    buttonColor = j.optString("button_color", "#F3F7EF"),
                    readerColor = j.optString("reader_color", "#E8EDF2"),
                    outlineColor = j.optString("outline_color", "#000000"),
                    fx = j.optString("theme_fx", "none")
                )
            } catch (_: Exception) { null }
        } ?: emptyList()
        return builtins + extra.sortedBy { it.name.lowercase() }
    }

    fun save(context: Context, name: String, app: String, button: String, reader: String, outline: String): VisualTheme {
        val slug = name.lowercase().replace(Regex("[^a-z0-9]+"), "-").trim('-').ifBlank { "theme" }
        if (builtins.any { it.id == slug || it.name.equals(name.trim(), true) }) {
            throw IllegalArgumentException("Built-in themes cannot be overwritten")
        }
        val theme = VisualTheme(slug, name.trim().ifBlank { slug }, false, "Custom saved look", app, button, reader, outline)
        val json = JSONObject()
            .put("id", theme.id)
            .put("name", theme.name)
            .put("blurb", theme.blurb)
            .put("app_color", theme.appColor)
            .put("button_color", theme.buttonColor)
            .put("reader_color", theme.readerColor)
            .put("outline_color", theme.outlineColor)
            .put("theme_fx", theme.fx)
        File(dir(context), "${theme.id}.json").writeText(json.toString())
        return theme
    }

    fun delete(context: Context, ids: Collection<String>): Int {
        var n = 0
        ids.forEach { id ->
            if (builtins.any { it.id == id }) return@forEach
            val f = File(dir(context), "$id.json")
            if (f.exists() && f.delete()) n++
        }
        return n
    }
}
