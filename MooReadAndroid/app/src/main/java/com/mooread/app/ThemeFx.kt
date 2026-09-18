package com.mooread.app

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.Rect
import android.graphics.Shader
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.LayerDrawable
import android.os.Build
import android.os.SystemClock
import android.view.Choreographer
import android.view.View
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import androidx.annotation.RequiresApi
import android.graphics.RenderEffect
import android.graphics.RuntimeShader

/**
 * Whole-app look for built-in themes.
 *
 * On API 33+ the AGSL shader is attached as a RenderEffect on the content
 * root so every pixel — chrome, wallpaper, reader — is processed.
 * Older devices get a non-interactive overlay drawable (scanlines / LCD
 * grid / platinum sheen) plus a ColorMatrix on the wallpaper.
 */
object ThemeFx {
    const val NONE = "none"
    const val AMBER = "amber-crt"
    const val PLATINUM = "mac-platinum"
    const val DMG = "gameboy-dmg"

    // Keep in lockstep with mooread/theme_fx.py AGSL_SHADER.
    const val AGSL = """
uniform shader uContent;
uniform float2 iResolution;
uniform float uTime;
uniform float uMode;

half4 main(float2 fragCoord) {
    float2 uv = fragCoord / max(iResolution, float2(1.0, 1.0));
    float2 centered = uv * 2.0 - 1.0;
    float mode = uMode;
    float2 px = fragCoord;
    px.x = clamp(px.x, 0.5, iResolution.x - 0.5);
    px.y = clamp(px.y, 0.5, iResolution.y - 0.5);
    half4 color = uContent.eval(px);
    float lum = dot(float3(color.r, color.g, color.b), float3(0.299, 0.587, 0.114));

    if (mode > 0.5 && mode < 1.5) {
        float3 amber = float3(1.0, 0.62, 0.0);
        float3 phosphor = float3(lum, lum, lum) * amber * 1.35;
        phosphor += amber * 0.18 * lum * lum;
        float scan = 0.55 + 0.45 * sin(fragCoord.y * 3.14159);
        float flicker = 0.92 + 0.08 * sin(uTime * 37.0);
        float vig = 1.0 - 0.55 * dot(centered, centered);
        phosphor *= scan * flicker * vig;
        color = half4(half3(phosphor), color.a);
    } else if (mode > 1.5 && mode < 2.5) {
        float lifted = clamp(lum * 1.08 + 0.06, 0.0, 1.0);
        float3 silver = float3(lifted * 0.90, lifted * 0.90, lifted * 0.96);
        silver += float3(0.07 * (1.0 - uv.y));
        color = half4(half3(silver), color.a);
    } else if (mode > 2.5) {
        float3 dark = float3(0.059, 0.220, 0.059);
        float3 mid = float3(0.188, 0.384, 0.188);
        float3 lite = float3(0.545, 0.675, 0.059);
        float3 lite2 = float3(0.608, 0.737, 0.059);
        float3 lcd = dark;
        if (lum >= 0.22 && lum < 0.45) lcd = mid;
        else if (lum >= 0.45 && lum < 0.72) lcd = lite;
        else if (lum >= 0.72) lcd = lite2;
        float grid = 1.0;
        if (mod(fragCoord.x, 3.0) < 0.85 || mod(fragCoord.y, 3.0) < 0.85) {
            grid = 0.62;
        }
        lcd *= grid;
        float vig = 1.0 - 0.32 * dot(centered, centered);
        color = half4(half3(lcd * vig), color.a);
    }
    return color;
}
"""

    fun normalize(themeId: String?, explicitFx: String? = null): String {
        val ids = listOf(explicitFx, themeId).map { it?.lowercase()?.trim().orEmpty() }
        return ids.firstOrNull { it == AMBER || it == PLATINUM || it == DMG } ?: NONE
    }

    fun mode(fx: String): Float = when (normalize(fx)) {
        AMBER -> 1f
        PLATINUM -> 2f
        DMG -> 3f
        else -> 0f
    }

    fun wallpaperFilter(fx: String): ColorMatrixColorFilter? {
        return when (normalize(fx)) {
            AMBER -> ColorMatrixColorFilter(ColorMatrix(floatArrayOf(
                0.393f, 0.349f, 0.272f, 0f, 8f,
                0.222f, 0.197f, 0.154f, 0f, 4f,
                0.000f, 0.000f, 0.000f, 0f, 0f,
                0f, 0f, 0f, 1f, 0f
            )))
            PLATINUM -> ColorMatrixColorFilter(ColorMatrix().apply { setSaturation(0f) })
            DMG -> ColorMatrixColorFilter(ColorMatrix(floatArrayOf(
                0.20f, 0.45f, 0.05f, 0f, 8f,
                0.30f, 0.55f, 0.08f, 0f, 16f,
                0.05f, 0.20f, 0.05f, 0f, 8f,
                0f, 0f, 0f, 1f, 0f
            )))
            else -> null
        }
    }

    fun buttonBackground(fx: String): Drawable {
        return when (normalize(fx)) {
            AMBER -> bevel(0xFF2A1604.toInt(), 0xFF4A2200.toInt(), 0xFF140C04.toInt(), 2)
            PLATINUM -> bevel(0xFFE8E8E8.toInt(), 0xFFFFFFFF.toInt(), 0xFF808080.toInt(), 2)
            DMG -> bevel(0xFF306230.toInt(), 0xFF8BAC0F.toInt(), 0xFF0F380F.toInt(), 3)
            else -> GradientDrawable().apply {
                setColor(0xFF2A3138.toInt())
                cornerRadius = 8f
            }
        }
    }

    fun playerColor(fx: String): Int = when (normalize(fx)) {
        AMBER -> 0xFF0A0602.toInt()
        PLATINUM -> 0xFFA8A8A8.toInt()
        DMG -> 0xFF0B2A0B.toInt()
        else -> 0xFF0B0D10.toInt()
    }

    private fun bevel(face: Int, hi: Int, lo: Int, stroke: Int): Drawable {
        val body = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(hi, face)).apply {
            cornerRadius = if (stroke >= 3) 2f else 0f
        }
        val border = GradientDrawable().apply {
            setColor(Color.TRANSPARENT)
            setStroke(stroke, lo)
            cornerRadius = if (stroke >= 3) 2f else 0f
        }
        return LayerDrawable(arrayOf(body, border))
    }
}

class ThemeFxDrawable(private var fx: String) : Drawable(), Choreographer.FrameCallback {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var time = 0f
    private var running = false

    fun setFx(value: String) {
        fx = ThemeFx.normalize(value)
        invalidateSelf()
        if (fx == ThemeFx.AMBER) start() else stop()
    }

    fun start() {
        if (running) return
        running = true
        Choreographer.getInstance().postFrameCallback(this)
    }

    fun stop() {
        running = false
        Choreographer.getInstance().removeFrameCallback(this)
    }

    override fun doFrame(frameTimeNanos: Long) {
        if (!running) return
        time = (SystemClock.uptimeMillis() % 100000L) / 1000f
        invalidateSelf()
        Choreographer.getInstance().postFrameCallback(this)
    }

    override fun draw(canvas: Canvas) {
        val b = bounds
        if (b.isEmpty) return
        when (ThemeFx.normalize(fx)) {
            ThemeFx.AMBER -> drawCrt(canvas, b)
            ThemeFx.PLATINUM -> drawPlatinum(canvas, b)
            ThemeFx.DMG -> drawDmg(canvas, b)
        }
    }

    private fun drawCrt(canvas: Canvas, b: Rect) {
        paint.shader = null
        paint.strokeWidth = 1f
        val flicker = (0.10f + 0.04f * kotlin.math.sin(time * 37.0).toFloat())
        paint.color = Color.argb((120 * flicker).toInt().coerceIn(40, 140), 0, 0, 0)
        var y = b.top + ((time * 18f) % 2f).toInt()
        while (y < b.bottom) {
            canvas.drawLine(b.left.toFloat(), y.toFloat(), b.right.toFloat(), y.toFloat(), paint)
            y += 2
        }
        val rollY = b.top + ((time * 70f) % b.height().coerceAtLeast(1))
        paint.color = Color.argb(28, 255, 176, 0)
        canvas.drawRect(b.left.toFloat(), rollY, b.right.toFloat(), rollY + 6f, paint)
        paint.shader = LinearGradient(
            b.exactCenterX(), b.top.toFloat(), b.exactCenterX(), b.bottom.toFloat(),
            intArrayOf(Color.argb(40, 0, 0, 0), Color.TRANSPARENT, Color.argb(70, 20, 8, 0)),
            floatArrayOf(0f, 0.5f, 1f),
            Shader.TileMode.CLAMP
        )
        canvas.drawRect(b, paint)
        paint.shader = null
    }

    private fun drawPlatinum(canvas: Canvas, b: Rect) {
        paint.shader = LinearGradient(
            b.left.toFloat(), b.top.toFloat(), b.left.toFloat(), b.bottom.toFloat(),
            intArrayOf(Color.argb(50, 255, 255, 255), Color.TRANSPARENT, Color.argb(30, 0, 0, 0)),
            floatArrayOf(0f, 0.18f, 1f),
            Shader.TileMode.CLAMP
        )
        canvas.drawRect(b, paint)
        paint.shader = null
        paint.color = Color.argb(60, 255, 255, 255)
        canvas.drawRect(b.left.toFloat(), b.top.toFloat(), b.right.toFloat(), b.top + 1f, paint)
        paint.color = Color.argb(80, 80, 80, 80)
        canvas.drawRect(b.left.toFloat(), b.bottom - 1f, b.right.toFloat(), b.bottom.toFloat(), paint)
    }

    private fun drawDmg(canvas: Canvas, b: Rect) {
        paint.shader = null
        paint.color = Color.argb(90, 15, 56, 15)
        paint.strokeWidth = 1f
        var y = b.top
        while (y < b.bottom) {
            canvas.drawLine(b.left.toFloat(), y.toFloat(), b.right.toFloat(), y.toFloat(), paint)
            y += 3
        }
        var x = b.left
        paint.color = Color.argb(28, 15, 56, 15)
        while (x < b.right) {
            canvas.drawLine(x.toFloat(), b.top.toFloat(), x.toFloat(), b.bottom.toFloat(), paint)
            x += 3
        }
        paint.shader = LinearGradient(
            b.exactCenterX(), b.top.toFloat(), b.exactCenterX(), b.bottom.toFloat(),
            intArrayOf(Color.argb(35, 155, 188, 15), Color.TRANSPARENT, Color.argb(55, 15, 56, 15)),
            floatArrayOf(0f, 0.4f, 1f),
            Shader.TileMode.CLAMP
        )
        canvas.drawRect(b, paint)
        paint.shader = null
    }

    override fun setAlpha(alpha: Int) { paint.alpha = alpha }
    override fun setColorFilter(colorFilter: ColorFilter?) { paint.colorFilter = colorFilter }
    @Deprecated("Deprecated in Java")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
}

class ThemeFxController(private val content: View) {
    private val overlay = ThemeFxDrawable(ThemeFx.NONE)
    private var currentFx = ThemeFx.NONE
    private var generation = 0
    private var frameCallback: Choreographer.FrameCallback? = null
    private var posted: Runnable? = null
    private var overlayLayout: View.OnLayoutChangeListener? = null
    private var shaderLayout: View.OnLayoutChangeListener? = null

    fun apply(fxRaw: String?, wallpaper: ImageView?, buttons: List<Button>, extraText: List<TextView> = emptyList()) {
        generation += 1
        val gen = generation
        val fx = ThemeFx.normalize(fxRaw)
        currentFx = fx
        detachFx()
        wallpaper?.colorFilter = ThemeFx.wallpaperFilter(fx)
        buttons.forEach { btn ->
            btn.background = ThemeFx.buttonBackground(fx)
            btn.minHeight = (48 * content.resources.displayMetrics.density).toInt()
        }
        extraText.forEach { tv ->
            tv.typeface = if (fx == ThemeFx.AMBER || fx == ThemeFx.DMG) {
                android.graphics.Typeface.MONOSPACE
            } else {
                android.graphics.Typeface.SANS_SERIF
            }
        }
        if (fx == ThemeFx.NONE) return

        val run = Runnable {
            if (gen != generation || currentFx != fx) return@Runnable
            overlay.setFx(fx)
            overlay.setBounds(0, 0, content.width.coerceAtLeast(1), content.height.coerceAtLeast(1))
            content.overlay.add(overlay)
            if (fx == ThemeFx.AMBER) overlay.start()
            val lay = View.OnLayoutChangeListener { v, _, _, _, _, _, _, _, _ ->
                if (gen != generation || currentFx != fx) return@OnLayoutChangeListener
                overlay.setBounds(0, 0, v.width.coerceAtLeast(1), v.height.coerceAtLeast(1))
            }
            overlayLayout = lay
            content.addOnLayoutChangeListener(lay)
            if (Build.VERSION.SDK_INT >= 31) {
                val filter = ThemeFx.wallpaperFilter(fx)
                if (filter != null) {
                    try { content.setRenderEffect(RenderEffect.createColorFilterEffect(filter)) } catch (_: Throwable) {}
                }
            }
            if (Build.VERSION.SDK_INT >= 33) {
                try { attachShader(fx, gen) } catch (_: Throwable) {}
            }
        }
        posted = run
        if (content.width > 0 && content.height > 0) run.run() else content.post(run)
    }

    @RequiresApi(33)
    private fun attachShader(fx: String, gen: Int) {
        if (gen != generation || currentFx != fx) return
        content.setLayerType(View.LAYER_TYPE_HARDWARE, null)
        val rt = RuntimeShader(ThemeFx.AGSL)
        val applyUniforms = {
            if (gen == generation && currentFx == fx) {
                val w = content.width.coerceAtLeast(1).toFloat()
                val h = content.height.coerceAtLeast(1).toFloat()
                rt.setFloatUniform("iResolution", w, h)
                rt.setFloatUniform("uTime", (SystemClock.uptimeMillis() % 100000L) / 1000f)
                rt.setFloatUniform("uMode", ThemeFx.mode(fx))
                content.setRenderEffect(RenderEffect.createRuntimeShaderEffect(rt, "uContent"))
            }
        }
        applyUniforms()
        val cb = Choreographer.FrameCallback {
            if (gen != generation || currentFx != fx) return@FrameCallback
            try { applyUniforms() } catch (_: Throwable) {}
            if (currentFx == ThemeFx.AMBER) {
                Choreographer.getInstance().postFrameCallback(frameCallback)
            }
        }
        frameCallback = cb
        if (fx == ThemeFx.AMBER) Choreographer.getInstance().postFrameCallback(cb)
        val lay = View.OnLayoutChangeListener { _, _, _, _, _, _, _, _, _ ->
            if (gen != generation || currentFx != fx) return@OnLayoutChangeListener
            try { applyUniforms() } catch (_: Throwable) {}
        }
        shaderLayout = lay
        content.addOnLayoutChangeListener(lay)
    }

    private fun detachFx() {
        posted?.let { content.removeCallbacks(it) }
        posted = null
        stopFrames()
        overlayLayout?.let { content.removeOnLayoutChangeListener(it) }
        shaderLayout?.let { content.removeOnLayoutChangeListener(it) }
        overlayLayout = null
        shaderLayout = null
        content.overlay.clear()
        overlay.stop()
        overlay.setFx(ThemeFx.NONE)
        if (Build.VERSION.SDK_INT >= 31) {
            try { content.setRenderEffect(null) } catch (_: Throwable) {}
        }
        content.setLayerType(View.LAYER_TYPE_NONE, null)
    }

    private fun stopFrames() {
        frameCallback?.let { Choreographer.getInstance().removeFrameCallback(it) }
        frameCallback = null
        overlay.stop()
    }
}
