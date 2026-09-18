package com.mooread.app

import android.graphics.SurfaceTexture
import android.media.MediaPlayer
import android.net.Uri
import android.view.Surface
import android.view.TextureView
import android.view.View

/**
 * Wallpaper video. Loops the file itself (not the reader Loop button).
 * TextureView stays under the reader instead of a SurfaceView punch-through.
 */
class WallpaperPlayer(private val view: TextureView) : TextureView.SurfaceTextureListener {
    private var player: MediaPlayer? = null
    private var pending: Uri? = null
    private var muted = true
    private var surface: Surface? = null

    init {
        view.surfaceTextureListener = this
    }

    fun play(uri: Uri, muted: Boolean) {
        this.muted = muted
        pending = uri
        view.visibility = View.VISIBLE
        val st = view.surfaceTexture
        if (st != null) start(uri, Surface(st))
    }

    fun setMuted(value: Boolean) {
        muted = value
        val vol = if (muted) 0f else 1f
        try { player?.setVolume(vol, vol) } catch (_: Exception) {}
    }

    fun stop() {
        pending = null
        try { player?.stop() } catch (_: Exception) {}
        try { player?.release() } catch (_: Exception) {}
        player = null
        view.visibility = View.GONE
    }

    override fun onSurfaceTextureAvailable(st: SurfaceTexture, width: Int, height: Int) {
        val uri = pending ?: return
        start(uri, Surface(st))
    }

    override fun onSurfaceTextureSizeChanged(st: SurfaceTexture, width: Int, height: Int) {}

    override fun onSurfaceTextureDestroyed(st: SurfaceTexture): Boolean {
        try { player?.setSurface(null) } catch (_: Exception) {}
        surface?.release()
        surface = null
        return true
    }

    override fun onSurfaceTextureUpdated(st: SurfaceTexture) {}

    private fun start(uri: Uri, surf: Surface) {
        stopPlayerOnly()
        surface = surf
        val mp = MediaPlayer()
        player = mp
        try {
            mp.isLooping = true
            mp.setSurface(surf)
            mp.setDataSource(view.context, uri)
            val vol = if (muted) 0f else 1f
            mp.setVolume(vol, vol)
            mp.setOnPreparedListener {
                it.isLooping = true
                it.start()
            }
            // Belt and braces: some devices ignore isLooping.
            mp.setOnCompletionListener { ended ->
                try {
                    ended.isLooping = true
                    ended.seekTo(0)
                    ended.start()
                } catch (_: Exception) {}
            }
            mp.prepareAsync()
        } catch (_: Exception) {
            stop()
        }
    }

    private fun stopPlayerOnly() {
        try { player?.stop() } catch (_: Exception) {}
        try { player?.release() } catch (_: Exception) {}
        player = null
        surface?.release()
        surface = null
    }
}
