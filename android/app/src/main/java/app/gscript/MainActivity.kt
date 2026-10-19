package app.gscript

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.webkit.JavascriptInterface
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * g-script for Android: a full-screen window onto the phone page served by your PC,
 * plus an optional background watcher that alerts you when the AI is done.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private lateinit var setup: LinearLayout
    private lateinit var linkInput: EditText
    private lateinit var errorBox: LinearLayout
    private lateinit var errorText: TextView
    private var failed = false

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this)
        root.setBackgroundColor(BG)

        web = WebView(this)
        web.setBackgroundColor(BG)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.userAgentString = web.settings.userAgentString + " GScriptApp/1"
        web.addJavascriptInterface(Bridge(), "GScriptAndroid")
        web.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                failed = false
                errorBox.visibility = View.GONE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                if (!failed) errorBox.visibility = View.GONE
            }

            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                if (request != null && request.isForMainFrame) {
                    failed = true
                    errorText.text = "Can't reach your PC.\n\nIs g-script running there, and are you on the right network?"
                    errorBox.visibility = View.VISIBLE
                }
            }

            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val target = request?.url ?: return false
                val base = Uri.parse(Prefs.server(this@MainActivity))
                if (target.host == base.host) return false
                startActivity(Intent(Intent.ACTION_VIEW, target))
                return true
            }
        }
        root.addView(web, FrameLayout.LayoutParams(MATCH, MATCH))

        // ----- shown when the PC can't be reached -----
        errorText = label("", 16f, false, Color.WHITE)
        errorBox = LinearLayout(this)
        errorBox.orientation = LinearLayout.VERTICAL
        errorBox.gravity = Gravity.CENTER
        errorBox.setBackgroundColor(BG)
        errorBox.setPadding(dp(28), dp(28), dp(28), dp(28))
        errorBox.visibility = View.GONE
        errorBox.addView(errorText)
        errorBox.addView(button("Try again") {
            errorBox.visibility = View.GONE
            web.loadUrl(Prefs.normalize(Prefs.server(this)))
        })
        errorBox.addView(button("Change PC link") { showSetup() })
        root.addView(errorBox, FrameLayout.LayoutParams(MATCH, MATCH))

        // ----- first-run screen: paste the PC link -----
        linkInput = EditText(this)
        linkInput.hint = "http://... or https://..."
        linkInput.setSingleLine(true)
        linkInput.setTextColor(Color.WHITE)
        linkInput.setHintTextColor(Color.parseColor("#6F7B87"))
        linkInput.setBackgroundColor(Color.parseColor("#1B2027"))
        linkInput.setPadding(dp(14), dp(12), dp(14), dp(12))
        linkInput.imeOptions = EditorInfo.IME_ACTION_GO
        linkInput.setOnEditorActionListener { _, _, _ ->
            connect(linkInput.text.toString())
            true
        }

        setup = LinearLayout(this)
        setup.orientation = LinearLayout.VERTICAL
        setup.gravity = Gravity.CENTER
        setup.setBackgroundColor(BG)
        setup.setPadding(dp(28), dp(28), dp(28), dp(28))
        setup.addView(label("g-script", 30f, true, Color.WHITE))
        setup.addView(label("Paste the Wi-Fi link from the g-script window on your PC. Your phone must be on the same Wi-Fi.", 15f, false, GRAY))
        setup.addView(linkInput)
        setup.addView(button("Connect") { connect(linkInput.text.toString()) })
        setup.addView(label("Tip: you can also Share the link to g-script from any app.", 13f, false, GRAY))
        root.addView(setup, FrameLayout.LayoutParams(MATCH, MATCH))

        setContentView(root)

        val handled = handle(intent)
        if (!handled) {
            if (Prefs.server(this).isEmpty()) {
                showSetup()
            } else {
                showWeb()
                web.loadUrl(Prefs.normalize(Prefs.server(this)))
            }
        }
        syncAlerts()
    }

    // ---------- small view helpers ----------
    private fun label(t: String, size: Float, bold: Boolean, color: Int): TextView {
        val v = TextView(this)
        v.text = t
        v.textSize = size
        v.setTextColor(color)
        v.gravity = Gravity.CENTER
        v.setPadding(0, dp(10), 0, dp(10))
        if (bold) v.setTypeface(v.typeface, Typeface.BOLD)
        return v
    }

    private fun button(t: String, onClick: () -> Unit): Button {
        val b = Button(this)
        b.text = t
        b.isAllCaps = false
        b.setOnClickListener { onClick() }
        return b
    }

    private fun showSetup() {
        web.visibility = View.GONE
        errorBox.visibility = View.GONE
        setup.visibility = View.VISIBLE
    }

    private fun showWeb() {
        setup.visibility = View.GONE
        web.visibility = View.VISIBLE
    }

    // ---------- connecting ----------
    private fun extractLink(raw: String): String {
        val m = Regex("https?://\\S+").find(raw)
        return if (m != null) m.value else raw.trim()
    }

    private fun connect(raw: String) {
        val full = Prefs.normalize(extractLink(raw))
        if (full.isEmpty()) {
            Toast.makeText(this, "Paste the link first", Toast.LENGTH_SHORT).show()
            return
        }
        Prefs.setServer(this, Prefs.origin(full))
        showWeb()
        web.loadUrl(full)
    }

    /** true if the intent carried a link (shared from another app) and we connected to it */
    private fun handle(i: Intent?): Boolean {
        if (i != null && i.action == Intent.ACTION_SEND) {
            val t = i.getStringExtra(Intent.EXTRA_TEXT)
            if (!t.isNullOrBlank()) {
                connect(t)
                return true
            }
        }
        return false
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    // ---------- alerts ----------
    private fun syncAlerts() {
        val on = Prefs.notify(this) && Prefs.token(this).isNotEmpty() && Prefs.server(this).isNotEmpty()
        if (on) {
            if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
            }
            WatchService.start(this)
        } else {
            WatchService.stop(this)
        }
    }

    /** What the phone page can ask the app to do (see app.html: window.GScriptAndroid). */
    inner class Bridge {
        @JavascriptInterface
        fun setToken(t: String?) {
            runOnUiThread {
                Prefs.setToken(this@MainActivity, t ?: "")
                syncAlerts()
            }
        }

        @JavascriptInterface
        fun setNotify(on: Boolean) {
            runOnUiThread {
                Prefs.setNotify(this@MainActivity, on)
                syncAlerts()
            }
        }

        @JavascriptInterface
        fun getNotify(): Boolean = Prefs.notify(this@MainActivity)

        @JavascriptInterface
        fun forget() {
            runOnUiThread {
                Prefs.setToken(this@MainActivity, "")
                Prefs.setServer(this@MainActivity, "")
                WatchService.stop(this@MainActivity)
                web.evaluateJavascript("localStorage.clear()", null)
                showSetup()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        visible = true
    }

    override fun onPause() {
        super.onPause()
        visible = false
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (web.visibility == View.VISIBLE && web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    companion object {
        /** true while the app is on screen, so the watcher doesn't notify about what you can already see */
        @Volatile
        var visible = false

        private val BG = Color.parseColor("#0F1216")
        private val GRAY = Color.parseColor("#8C98A4")
        private const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
    }
}
