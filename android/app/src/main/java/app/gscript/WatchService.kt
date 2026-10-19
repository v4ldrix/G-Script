package app.gscript

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Keeps watching your PC in the background (a normal foreground service with a small notification)
 * and alerts you when the AI finishes, needs your approval, or hits a problem.
 */
class WatchService : Service() {
    @Volatile
    private var running = false
    private var worker: Thread? = null
    private var shownText = ""

    override fun onBind(intent: Intent?): IBinder? = null

    @SuppressLint("InlinedApi")
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent != null && ACTION_STOP == intent.action) {
            Prefs.setNotify(this, false)
            stopSelf()
            return START_NOT_STICKY
        }
        channels()
        ServiceCompat.startForeground(this, 1, ongoing("Watching for your AI..."), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        if (!running) {
            running = true
            val t = Thread { loop() }
            t.isDaemon = true
            t.start()
            worker = t
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        worker?.interrupt()
        super.onDestroy()
    }

    // ---------- polling ----------
    private fun loop() {
        var last = -1L
        var failures = 0
        while (running) {
            val server = Prefs.server(this)
            val token = Prefs.token(this)
            if (server.isEmpty() || token.isEmpty() || !Prefs.notify(this)) {
                stopSelf()
                break
            }
            try {
                val since = if (last < 0) 0L else last
                val json = get(Prefs.origin(server) + "/state?since=" + since, token)
                val newLast = json.optLong("last", since)
                if (last >= 0) handle(json)   // the first poll only learns where we are: skip old history
                last = newLast
                failures = 0
                refreshOngoing(json)
            } catch (e: Exception) {
                failures++
                if (failures == 3) setOngoing("Can't reach your PC")
            }
            try {
                Thread.sleep(if (failures > 0) 8000L else 2500L)
            } catch (e: InterruptedException) {
                break
            }
        }
    }

    private fun get(url: String, token: String): JSONObject {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 8000
        c.readTimeout = 8000
        c.setRequestProperty("X-GScript-Token", token)
        try {
            if (c.responseCode != 200) throw IOException("HTTP " + c.responseCode)
            return JSONObject(c.inputStream.bufferedReader().use { it.readText() })
        } finally {
            c.disconnect()
        }
    }

    private fun handle(json: JSONObject) {
        if (MainActivity.visible) return
        val events = json.optJSONArray("events") ?: return
        for (i in 0 until events.length()) {
            val e = events.getJSONObject(i)
            val id = e.optInt("id")
            val text = e.optString("text")
            when (e.optString("type")) {
                "ai" -> alert(id, "g-script", if (text.isBlank()) "Done" else text.take(200))
                "approval" -> alert(id, "Approval needed", text)
                "error" -> alert(id, "g-script problem", text)
            }
        }
    }

    private fun refreshOngoing(json: JSONObject) {
        val studio = json.optJSONObject("studio")
        val ext = json.optJSONObject("ext")
        val studioOk = studio != null && studio.optBoolean("connected")
        val extOk = ext != null && ext.optBoolean("connected")
        setOngoing(
            when {
                !studioOk -> "Waiting for Roblox Studio"
                !extOk -> "Open an AI chat on your PC"
                else -> "Ready"
            }
        )
    }

    // ---------- notifications ----------
    private fun channels() {
        if (Build.VERSION.SDK_INT >= 26) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(CH_WATCH, "Connection", NotificationManager.IMPORTANCE_LOW))
            nm.createNotificationChannel(NotificationChannel(CH_ALERT, "Build updates", NotificationManager.IMPORTANCE_HIGH))
        }
    }

    private fun openApp(): PendingIntent {
        val i = Intent(this, MainActivity::class.java)
        i.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        return PendingIntent.getActivity(this, 0, i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    private fun ongoing(text: String): Notification {
        val stop = Intent(this, WatchService::class.java)
        stop.action = ACTION_STOP
        val stopIntent = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return NotificationCompat.Builder(this, CH_WATCH)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle("g-script")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(openApp())
            .addAction(0, "Stop alerts", stopIntent)
            .build()
    }

    private fun setOngoing(text: String) {
        if (text == shownText) return
        shownText = text
        try {
            getSystemService(NotificationManager::class.java).notify(1, ongoing(text))
        } catch (e: SecurityException) {
            // notifications are not allowed: nothing to update
        }
    }

    private fun alert(id: Int, title: String, text: String) {
        val n = NotificationCompat.Builder(this, CH_ALERT)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openApp())
            .build()
        try {
            getSystemService(NotificationManager::class.java).notify(1000 + id, n)
        } catch (e: SecurityException) {
            // notifications are not allowed: nothing to show
        }
    }

    companion object {
        const val ACTION_STOP = "app.gscript.STOP"
        private const val CH_WATCH = "watch"
        private const val CH_ALERT = "alerts"

        fun start(c: Context) {
            ContextCompat.startForegroundService(c, Intent(c, WatchService::class.java))
        }

        fun stop(c: Context) {
            c.stopService(Intent(c, WatchService::class.java))
        }
    }
}
