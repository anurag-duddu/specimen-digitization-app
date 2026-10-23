package org.fieldmuseum.specimen_digitization

import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.os.Bundle

/** Returns a fallback Custom Tab redirect to an existing auth attempt. */
class IntakeAuthCallbackActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val task = IntakeAuthActivity.deliverFallback(intent.data)
        if (task != null) {
            // The deep-link relay may be started from the browser task. Bring
            // the original Flutter task forward after its mediator returns.
            val manager = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            try {
                manager.appTasks.firstOrNull { it.taskInfo.taskId == task }?.moveToFront()
            } catch (_: SecurityException) {
                // The callback has still settled the original pending request.
            }
        }
        finish()
    }
}
