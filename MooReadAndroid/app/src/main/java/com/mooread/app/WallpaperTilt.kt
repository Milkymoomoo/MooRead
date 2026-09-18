package com.mooread.app

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.view.View
import kotlin.math.max
import kotlin.math.min

/**
 * Parallax wallpaper from device tilt. Wallpaper is scaled up so the
 * extra margin hides the edges while the view translates.
 */
class WallpaperTilt(
    context: Context,
    private val layers: List<View>
) : SensorEventListener {
    private val sensors = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val sensor = sensors.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    var enabled = false
        private set
    var aggressiveness = 0.45f
        set(value) {
            field = value.coerceIn(0f, 1f)
            applyScale()
            if (field <= 0.01f) snap(0f, 0f)
        }

    private var tx = 0f
    private var ty = 0f

    fun start() {
        enabled = true
        applyScale()
        sensor?.let { sensors.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
    }

    fun stop() {
        enabled = false
        sensors.unregisterListener(this)
        snap(0f, 0f)
        layers.forEach {
            it.scaleX = 1f
            it.scaleY = 1f
        }
    }

    fun applyScale() {
        val s = 1f + 0.18f * aggressiveness
        layers.forEach {
            it.scaleX = s
            it.scaleY = s
        }
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (!enabled || aggressiveness <= 0.01f) return
        val reach = 28f + 90f * aggressiveness
        val targetX = (-event.values[0] / 9.8f) * reach
        val targetY = (event.values[1] / 9.8f) * reach
        tx += (targetX - tx) * 0.18f
        ty += (targetY - ty) * 0.18f
        snap(tx, ty)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun snap(x: Float, y: Float) {
        val cx = max(-140f, min(140f, x))
        val cy = max(-140f, min(140f, y))
        layers.forEach {
            it.translationX = cx
            it.translationY = cy
        }
    }
}
