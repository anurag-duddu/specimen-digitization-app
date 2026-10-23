package org.fieldmuseum.specimen_digitization

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.browser.auth.AuthTabIntent
import java.lang.ref.WeakReference

/** Owns one system-browser authorization attempt and its Custom Tab fallback. */
class IntakeAuthActivity : ComponentActivity() {
    private var attemptId: String? = null
    private var expectedState: String? = null
    private var launched = false
    private var settled = false
    private val authLauncher = AuthTabIntent.registerActivityResultLauncher(this) { result ->
        if (attemptId == null) return@registerActivityResultLauncher
        when (result.resultCode) {
            AuthTabIntent.RESULT_OK -> complete(result.resultUri)
            AuthTabIntent.RESULT_CANCELED -> finishWith(error = "cancelled")
            else -> finishWith(error = "unavailable")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        attemptId = savedInstanceState?.getString(EXTRA_ID) ?: intent.getStringExtra(EXTRA_ID)
        expectedState = savedInstanceState?.getString(EXTRA_STATE)
            ?: intent.getStringExtra(EXTRA_STATE)
        launched = savedInstanceState?.getBoolean("launched") ?: false
        settled = savedInstanceState?.getBoolean("settled") ?: false
        val id = attemptId
        val state = expectedState
        val url = intent.getStringExtra(EXTRA_URL)?.let(Uri::parse)
        if (id.isNullOrEmpty() || state.isNullOrEmpty() || url?.scheme != "https") {
            finishWith(error = "unavailable")
            return
        }
        active = WeakReference(this)
        if (!launched) {
            launched = true
            try {
                // AndroidX starts a Custom Tab automatically when Auth Tab is
                // unsupported. Its redirect is delivered by our callback relay.
                AuthTabIntent.Builder().build().launch(authLauncher, url, "specimenintake")
            } catch (_: Exception) {
                finishWith(error = "unavailable")
            }
        }
    }

    override fun onDestroy() {
        if (active?.get() === this) active = null
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString(EXTRA_ID, attemptId)
        outState.putString(EXTRA_STATE, expectedState)
        outState.putBoolean("launched", launched)
        outState.putBoolean("settled", settled)
        super.onSaveInstanceState(outState)
    }

    private fun complete(uri: Uri?, ignoreMismatchedState: Boolean = false): Boolean {
        if (settled) return false
        val state = expectedState
        if (attemptId == null || state.isNullOrEmpty() ||
            uri?.scheme != "specimenintake" || uri.host != "oauth" ||
            uri.path != "/callback" || uri.port != -1 ||
            !uri.userInfo.isNullOrEmpty() || uri.encodedQuery != null) {
            if (!ignoreMismatchedState) finishWith(error = "invalid_callback")
            return false
        }
        val fragment = uri.encodedFragment ?: run {
            if (!ignoreMismatchedState) finishWith(error = "invalid_callback")
            return false
        }
        val fields = Uri.parse("https://callback.invalid/?$fragment")
        if (fields.getQueryParameters("state") != listOf(state)) {
            if (!ignoreMismatchedState) finishWith(error = "invalid_callback")
            return false
        }
        finishWith(callback = uri.toString())
        return true
    }

    private fun finishWith(callback: String? = null, error: String? = null) {
        if (settled) return
        settled = true
        if (active?.get() === this) active = null
        setResult(
            if (callback != null) Activity.RESULT_OK else Activity.RESULT_CANCELED,
            Intent().putExtra(EXTRA_ID, attemptId)
                .putExtra(EXTRA_CALLBACK, callback)
                .putExtra(EXTRA_ERROR, error),
        )
        finish()
    }

    companion object {
        private var active: WeakReference<IntakeAuthActivity>? = null

        fun cancel(id: String) {
            active?.get()?.takeIf { it.attemptId == id }?.finishWith(error = "cancelled")
        }

        /** Returns the existing app task only for the current valid redirect. */
        fun deliverFallback(uri: Uri?): Int? {
            val current = active?.get() ?: return null
            val task = current.taskId
            return if (current.complete(uri, ignoreMismatchedState = true)) task else null
        }

        const val EXTRA_ID = "intake_auth_id"
        const val EXTRA_URL = "intake_auth_url"
        const val EXTRA_STATE = "intake_auth_state"
        const val EXTRA_CALLBACK = "intake_auth_callback"
        const val EXTRA_ERROR = "intake_auth_error"
    }
}
