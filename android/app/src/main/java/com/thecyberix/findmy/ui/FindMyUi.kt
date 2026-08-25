package com.thecyberix.findmy.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.view.MotionEvent
import android.widget.FrameLayout
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.thecyberix.findmy.data.Accessory
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker

private val Bg = Color(0xFF0B1220)
private val Fg = Color(0xFFE8EEF6)
private val Accent = Color(0xFF6EE7B7)
private val AccentDim = Color(0xFF1B3A2F)
private val Muted = Color(0xFF94A3B8)
private val Error = Color(0xFFFCA5A5)

@Composable
fun FindMyRoot(vm: FindMyViewModel = viewModel()) {
    val state by vm.state.collectAsState()
    MaterialTheme(colorScheme = darkColorScheme(background = Bg, surface = Bg, onBackground = Fg)) {
        Column(
            Modifier
                .fillMaxSize()
                .background(Bg)
                .padding(16.dp),
        ) {
            when {
                state.booting -> Text("…")
                !state.signedIn && !state.needs2fa -> LoginScreen(state, vm)
                state.needs2fa -> TwoFactorScreen(state, vm)
                else -> HomeScreen(state, vm)
            }
        }
    }
}

@Composable
private fun AppButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    selected: Boolean = false,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (selected) Accent else AccentDim,
            contentColor = if (selected) Bg else Fg,
            disabledContainerColor = AccentDim.copy(alpha = 0.4f),
            disabledContentColor = Fg.copy(alpha = 0.4f),
        ),
    ) {
        Text(label)
    }
}

@Composable
private fun LoginScreen(state: UiState, vm: FindMyViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("FindMy", style = MaterialTheme.typography.headlineMedium)
        OutlinedTextField(state.email, vm::setEmail, label = { Text("Apple ID") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(state.password, vm::setPassword, label = { Text("Password") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        state.error?.let { Text(it, color = Error) }
        AppButton("Sign in", onClick = vm::login, enabled = !state.busy, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun TwoFactorScreen(state: UiState, vm: FindMyViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("2FA", style = MaterialTheme.typography.headlineMedium)
        state.methods.forEach { method ->
            AppButton(
                label = method.label,
                onClick = { vm.setMethod(method.index) },
                selected = state.methodIndex == method.index,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        AppButton("Send", onClick = vm::sendCode, enabled = !state.busy, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(state.code, vm::setCode, label = { Text("Code") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        state.error?.let { Text(it, color = Error) }
        AppButton("Continue", onClick = vm::submitCode, enabled = !state.busy, modifier = Modifier.fillMaxWidth())
        AppButton("Cancel", onClick = vm::logout, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun HomeScreen(state: UiState, vm: FindMyViewModel) {
    val context = LocalContext.current
    val pickJson = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val name = uri.lastPathSegment?.substringAfterLast('/')?.removeSuffix(".json") ?: "AirTag"
        val text = context.contentResolver.openInputStream(uri)?.bufferedReader()?.readText()
            ?: return@rememberLauncherForActivityResult
        vm.importJson(text, name)
    }
    val notifyPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        vm.setAlerts(granted)
    }
    val selected = state.accessories.find { it.id == state.selectedId }

    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("FindMy", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            AppButton("Sign out", onClick = vm::logout)
        }
        Column(
            Modifier
                .fillMaxWidth()
                .heightIn(max = 160.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            state.accessories.forEach { tag ->
                AppButton(
                    label = tag.name,
                    onClick = { vm.select(tag.id) },
                    selected = tag.id == state.selectedId,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
        Column(
            Modifier
                .fillMaxWidth()
                .weight(1f, fill = true),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            TagMap(
                tag = selected,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f, fill = true),
            )
            TagStatusBar(tag = selected)
        }
        state.error?.let { Text(it, color = Error) }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            AppButton("Refresh", onClick = vm::refresh, enabled = !state.busy, modifier = Modifier.weight(1f))
            AppButton("Add", onClick = { pickJson.launch("application/json") }, enabled = !state.busy, modifier = Modifier.weight(1f))
            AppButton("Remove", onClick = vm::removeSelected, enabled = !state.busy && selected != null, modifier = Modifier.weight(1f))
        }
        AppButton(
            label = if (state.alerts) "Alerts 20:00 on" else "Alerts 20:00 off",
            onClick = {
                val on = !state.alerts
                if (on && Build.VERSION.SDK_INT >= 33 &&
                    ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED
                ) {
                    notifyPerm.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else {
                    vm.setAlerts(on)
                }
            },
            selected = state.alerts,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun TagStatusBar(tag: Accessory?) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(AccentDim)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        if (tag == null) {
            Text("Select an AirTag", color = Muted, style = MaterialTheme.typography.bodyMedium)
            return
        }
        Text(tag.name, color = Accent, style = MaterialTheme.typography.titleSmall)
        Text(
            "Battery: ${tag.battery}",
            color = Fg,
            style = MaterialTheme.typography.bodyMedium,
        )
        Text(
            "Last seen: ${formatLastSeen(tag.location?.timestamp)}",
            color = Fg,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

private fun formatLastSeen(iso: String?): String {
    if (iso.isNullOrBlank()) return "No report yet"
    return iso.take(19).replace('T', ' ')
}

@Composable
private fun TagMap(tag: Accessory?, modifier: Modifier = Modifier) {
    val lat = tag?.location?.latitude
    val lon = tag?.location?.longitude
    val tagKey = "${tag?.id}:${lat}:${lon}"
    val mapView = remember { arrayOfNulls<MapView>(1) }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            FrameLayout(ctx).apply {
                val map = MapView(ctx).apply {
                    setTileSource(TileSourceFactory.MAPNIK)
                    setMultiTouchControls(true)
                    isHorizontalMapRepetitionEnabled = false
                    isVerticalMapRepetitionEnabled = false
                    // Keep Compose parents from stealing drag/zoom gestures.
                    setOnTouchListener { v, event ->
                        when (event.actionMasked) {
                            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE ->
                                v.parent?.requestDisallowInterceptTouchEvent(true)
                            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL ->
                                v.parent?.requestDisallowInterceptTouchEvent(false)
                        }
                        false
                    }
                }
                mapView[0] = map
                addView(
                    map,
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT,
                        FrameLayout.LayoutParams.MATCH_PARENT,
                    ),
                )
            }
        },
        update = { container ->
            val map = mapView[0] ?: return@AndroidView
            val previous = container.getTag(com.thecyberix.findmy.R.id.map_focus_key) as? String
            if (previous == tagKey) return@AndroidView
            container.setTag(com.thecyberix.findmy.R.id.map_focus_key, tagKey)

            map.overlays.removeAll { it is Marker }
            val point = if (lat != null && lon != null) GeoPoint(lat, lon) else GeoPoint(20.0, 0.0)
            map.controller.setZoom(if (lat != null) 15.0 else 2.0)
            map.controller.setCenter(point)
            if (lat != null && lon != null) {
                val marker = Marker(map)
                marker.position = point
                marker.setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                marker.title = tag?.name
                map.overlays.add(marker)
            }
            map.invalidate()
        },
    )

    DisposableEffect(Unit) {
        onDispose {
            mapView[0]?.onDetach()
            mapView[0] = null
        }
    }
}
