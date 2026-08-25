package com.thecyberix.findmy.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.thecyberix.findmy.data.Accessory
import com.thecyberix.findmy.data.PythonBridge
import com.thecyberix.findmy.data.SessionStore
import com.thecyberix.findmy.data.TwoFactorMethod
import com.thecyberix.findmy.notify.DailyScheduler
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class UiState(
    val booting: Boolean = true,
    val signedIn: Boolean = false,
    val needs2fa: Boolean = false,
    val email: String = "",
    val password: String = "",
    val code: String = "",
    val methods: List<TwoFactorMethod> = emptyList(),
    val methodIndex: Int = 0,
    val accessories: List<Accessory> = emptyList(),
    val selectedId: String? = null,
    val alerts: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
)

class FindMyViewModel(app: Application) : AndroidViewModel(app) {
    private val store = SessionStore(app)
    private val _state = MutableStateFlow(UiState(alerts = store.alertsEnabled))
    val state: StateFlow<UiState> = _state

    init {
        viewModelScope.launch {
            val account = store.accountJson
            if (account != null) {
                val res = withContext(Dispatchers.IO) {
                    PythonBridge.restore(account, store.accessoriesJson)
                }
                if (res.ok) {
                    val tags = res.accessories ?: emptyList()
                    _state.update {
                        it.copy(
                            booting = false,
                            signedIn = true,
                            email = store.email,
                            accessories = tags,
                            selectedId = tags.firstOrNull()?.id,
                            alerts = store.alertsEnabled,
                        )
                    }
                    return@launch
                }
            }
            _state.update { it.copy(booting = false) }
        }
    }

    fun setEmail(value: String) = _state.update { it.copy(email = value, error = null) }
    fun setPassword(value: String) = _state.update { it.copy(password = value, error = null) }
    fun setCode(value: String) = _state.update { it.copy(code = value, error = null) }
    fun setMethod(index: Int) = _state.update { it.copy(methodIndex = index) }
    fun select(id: String) = _state.update { it.copy(selectedId = id) }

    fun setAlerts(enabled: Boolean) {
        store.alertsEnabled = enabled
        _state.update { it.copy(alerts = enabled) }
        if (enabled) DailyScheduler.schedule(getApplication())
    }

    fun login() {
        val s = _state.value
        run("Sign-in failed") {
            val res = PythonBridge.login(s.email, s.password)
            if (!res.ok) return@run res.error
            if (res.logged_in) {
                persist(res.account?.toString(), res.accessories.orEmpty(), s.email)
            }
            _state.update {
                it.copy(
                    signedIn = res.logged_in,
                    needs2fa = res.needs_2fa,
                    methods = res.methods,
                    methodIndex = res.methods.firstOrNull()?.index ?: 0,
                    accessories = res.accessories.orEmpty(),
                    selectedId = res.accessories?.firstOrNull()?.id,
                    password = "",
                )
            }
            null
        }
    }

    fun sendCode() {
        val index = _state.value.methodIndex
        run("Could not send code") {
            PythonBridge.request2fa(index).error
        }
    }

    fun submitCode() {
        val s = _state.value
        run("2FA failed") {
            val res = PythonBridge.submit2fa(s.methodIndex, s.code)
            if (!res.ok) return@run res.error
            persist(res.account?.toString(), res.accessories.orEmpty(), s.email)
            _state.update {
                it.copy(signedIn = true, needs2fa = false, code = "", accessories = res.accessories.orEmpty())
            }
            null
        }
    }

    fun refresh() {
        run("Refresh failed") {
            val account = store.accountJson ?: return@run "Not signed in."
            // Reload session from disk so Anisette v3 identity survives process pauses.
            val restored = PythonBridge.restore(account, store.accessoriesJson)
            if (!restored.ok) return@run restored.error ?: "Could not restore session."
            val res = PythonBridge.refresh()
            if (!res.ok) return@run res.error
            val tags = res.accessories.orEmpty()
            persist(PythonBridge.encodeAccount(res.account) ?: store.accountJson, tags, store.email)
            _state.update { it.copy(accessories = tags) }
            null
        }
    }

    fun importJson(text: String, name: String) {
        run("Import failed") {
            val res = PythonBridge.addAccessory(text, name)
            if (!res.ok) return@run res.error
            val tags = res.accessories.orEmpty()
            persist(store.accountJson, tags, store.email)
            _state.update {
                it.copy(accessories = tags, selectedId = res.accessory?.id ?: it.selectedId)
            }
            null
        }
    }

    fun removeSelected() {
        val id = _state.value.selectedId ?: return
        run("Remove failed") {
            val res = PythonBridge.removeAccessory(id)
            if (!res.ok) return@run res.error
            val tags = res.accessories.orEmpty()
            persist(store.accountJson, tags, store.email)
            _state.update { it.copy(accessories = tags, selectedId = tags.firstOrNull()?.id) }
            null
        }
    }

    fun logout() {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { PythonBridge.logout() }
            store.clear()
            _state.value = UiState(booting = false)
        }
    }

    private fun persist(accountJson: String?, tags: List<Accessory>, email: String) {
        store.email = email
        if (accountJson != null) store.accountJson = accountJson
        store.accessoriesJson = PythonBridge.encodeAccessories(tags)
    }

    private fun run(fallback: String, block: () -> String?) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            val err = withContext(Dispatchers.IO) {
                runCatching { block() }.getOrElse { it.message ?: fallback }
            }
            _state.update { it.copy(busy = false, error = err) }
        }
    }
}
