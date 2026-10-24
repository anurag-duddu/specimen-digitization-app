package org.fieldmuseum.specimen_digitization

import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.os.Bundle

/** Returns a fallback Custom Tab redirect to an existing auth attempt. */
class IntakeAuthCallbackActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val task = IntakeAuthActivity.deliverFallback(intent.data)
        if (task != null) {
            // The deep-link relay may be started from the browser task. The
            // mediator has already finished with its result, so clear any
            // remaining Auth Tab above the original FlutterActivity in that
            // exact task. This reuses MainActivity and its Flutter engine.
            val manager = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            try {
                manager.appTasks.firstOrNull { it.taskInfo.taskId == task }?.startActivity(
                    this,
                    Intent(this, MainActivity::class.java).apply {
                        addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    },
                    null,
                )
            } catch (_: RuntimeException) {
                // The callback result is already registered with the system.
            }
        }
        finish()
    }
}
