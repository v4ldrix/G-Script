package app.gscript

import android.content.Context
import android.net.Uri

/** Everything the app remembers: which PC to talk to, the pairing token, and the notification choice. */
object Prefs {
    private fun sp(c: Context) = c.getSharedPreferences("g", Context.MODE_PRIVATE)

    fun server(c: Context): String = sp(c).getString("server", "") ?: ""
    fun setServer(c: Context, v: String) {
        sp(c).edit().putString("server", v).apply()
    }

    fun token(c: Context): String = sp(c).getString("token", "") ?: ""
    fun setToken(c: Context, v: String) {
        sp(c).edit().putString("token", v).apply()
    }

    fun notify(c: Context): Boolean = sp(c).getBoolean("notify", true)
    fun setNotify(c: Context, v: Boolean) {
        sp(c).edit().putBoolean("notify", v).apply()
    }

    /** "192.168.1.5:8766", "http://...", "http://192.168.1.5:8766/app#pair=ABC" -> a URL the WebView can load. */
    fun normalize(raw: String): String {
        var s = raw.trim()
        if (s.isEmpty()) return ""
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "http://" + s
        val hash = s.indexOf('#')
        val frag = if (hash >= 0) s.substring(hash) else ""
        var base = if (hash >= 0) s.substring(0, hash) else s
        base = base.trimEnd('/')
        if (!base.endsWith("/app")) base += "/app"
        return base + frag
    }

    /** scheme://host[:port] of a link. */
    fun origin(url: String): String {
        val u = Uri.parse(url)
        return u.scheme + "://" + u.authority
    }
}
