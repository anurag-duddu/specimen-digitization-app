package org.fieldmuseum.specimen_digitization

import android.app.Activity
import android.content.Intent
import android.net.Uri
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var pendingId: String? = null
    private var pendingResult: MethodChannel.Result? = null
    private var pendingRequestCode: Int? = null
    private var nextRequestCode = 9117

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "specimen/intake_auth")
            .setMethodCallHandler { call, result ->
                val args = call.arguments as? Map<*, *>
                val id = args?.get("id") as? String
                if (id.isNullOrEmpty()) {
                    result.error("invalid_request", "Invalid connection request.", null)
                    return@setMethodCallHandler
                }
                when (call.method) {
                    "cancel" -> {
                        if (pendingId == id) {
                            finishPending(error = "cancelled")
                            IntakeAuthActivity.cancel(id)
                        }
                        result.success(null)
                    }
                    "authenticate" -> {
                        if (pendingId != null) {
                            result.error("busy", "A connection is already open.", null)
                            return@setMethodCallHandler
                        }
                        val url = args["url"] as? String
                        val state = args["state"] as? String
                        val uri = url?.let(Uri::parse)
                        if (uri?.scheme != "https" || uri.host.isNullOrEmpty() ||
                            !uri.userInfo.isNullOrEmpty() || state.isNullOrEmpty() ||
                            uri.getQueryParameters("state") != listOf(state)) {
                            result.error("invalid_request", "Invalid connection request.", null)
                            return@setMethodCallHandler
                        }
                        pendingId = id
                        pendingResult = result
                        val requestCode = nextRequestCode
                        nextRequestCode = if (nextRequestCode == 65534) 9117 else nextRequestCode + 1
                        pendingRequestCode = requestCode
                        try {
                            startActivityForResult(Intent(this, IntakeAuthActivity::class.java).apply {
                                putExtra(IntakeAuthActivity.EXTRA_ID, id)
                                putExtra(IntakeAuthActivity.EXTRA_URL, url)
                                putExtra(IntakeAuthActivity.EXTRA_STATE, state)
                            }, requestCode)
                        } catch (_: Exception) {
                            finishPending(error = "unavailable")
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != pendingRequestCode || pendingId == null) return
        if (data != null && data.getStringExtra(IntakeAuthActivity.EXTRA_ID) != pendingId) return
        val callback = data?.getStringExtra(IntakeAuthActivity.EXTRA_CALLBACK)
        if (resultCode == Activity.RESULT_OK && callback != null) {
            finishPending(callback = callback)
        } else {
            finishPending(error = data?.getStringExtra(IntakeAuthActivity.EXTRA_ERROR) ?: "cancelled")
        }
    }

    private fun finishPending(callback: String? = null, error: String? = null) {
        val result = pendingResult
        pendingResult = null
        pendingId = null
        pendingRequestCode = null
        if (error != null) result?.error(error, "Account connection ended.", null)
        else result?.success(callback)
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        finishPending(error = "cancelled")
        super.cleanUpFlutterEngine(flutterEngine)
    }
}
