package com.mooread.app

import android.content.Context
import android.net.Uri
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Best-effort Wallpaper Engine PKGV unpack + first playable media. */
object WallpaperPack {
    private val video = setOf("mp4", "webm", "mkv", "mov", "avi")
    private val image = setOf("png", "jpg", "jpeg", "webp", "bmp", "gif")

    fun import(context: Context, uri: Uri): File? {
        val name = uri.lastPathSegment?.substringAfterLast('/') ?: "wallpaper"
        val lower = name.lowercase()
        val destRoot = File(context.filesDir, "wallpaper-engine").apply { mkdirs() }
        if (lower.endsWith(".pkg") || lower.endsWith(".mpkg")) {
            val pkg = File(destRoot, "scene.pkg")
            context.contentResolver.openInputStream(uri)?.use { input ->
                pkg.outputStream().use { input.copyTo(it) }
            } ?: return null
            val unpacked = File(destRoot, "unpacked")
            unpackPkg(pkg, unpacked)
            return firstMedia(unpacked) ?: firstMedia(destRoot)
        }
        val ext = lower.substringAfterLast('.', "")
        val out = File(destRoot, "import.${ext.ifBlank { "bin" }}")
        context.contentResolver.openInputStream(uri)?.use { input ->
            out.outputStream().use { input.copyTo(it) }
        } ?: return null
        return out
    }

    fun firstMedia(folder: File): File? {
        if (!folder.exists()) return null
        val files = folder.walkTopDown().filter { it.isFile }.toList()
        files.firstOrNull { it.extension.lowercase() in video }?.let { return it }
        files.firstOrNull { it.name.startsWith("preview") && it.extension.lowercase() in image }?.let { return it }
        return files.firstOrNull { it.extension.lowercase() in image }
    }

    fun unpackPkg(pkg: File, dest: File): List<File> {
        val raw = pkg.readBytes()
        if (raw.size < 12 || raw[0] != 'P'.code.toByte() || raw[1] != 'K'.code.toByte() ||
            raw[2] != 'G'.code.toByte() || raw[3] != 'V'.code.toByte()
        ) return emptyList()
        dest.mkdirs()
        val buf = ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN)
        buf.position(8)
        if (buf.remaining() < 4) return emptyList()
        val count = buf.int.coerceIn(0, 20000)
        data class Ent(val name: String, val off: Int, val len: Int)
        val entries = ArrayList<Ent>(count)
        try {
            repeat(count) {
                val n = buf.int
                val bytes = ByteArray(n)
                buf.get(bytes)
                val name = bytes.toString(Charsets.UTF_8).replace('\\', '/').trimStart('/')
                val off = buf.int
                val len = buf.int
                entries += Ent(name, off, len)
            }
        } catch (_: Exception) {
            return emptyList()
        }
        val dataBase = buf.position()
        val written = mutableListOf<File>()
        for (e in entries) {
            if (e.name.isBlank() || ".." in e.name.split('/')) continue
            var start = dataBase + e.off
            if (start < 0 || start + e.len > raw.size) start = e.off
            if (start < 0 || start + e.len > raw.size) continue
            val out = File(dest, e.name)
            out.parentFile?.mkdirs()
            out.writeBytes(raw.copyOfRange(start, start + e.len))
            written += out
        }
        return written
    }
}
