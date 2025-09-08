#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descanso visual – Indicador de bandeja con temporizador trabajo/descanso.
Incluye:
- BreakWindow: ventana de descanso con botón "Salir del descanso".
- ConfirmWorkWindow: confirma si volver al trabajo.
- Integración con EyeCareApp: solo si el usuario confirma se reinician los minutos de trabajo.
"""

import os
import json
import signal
import argparse
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gtk, GLib, Notify, Gdk

# Intentar AppIndicator3/Ayatana (fallback)
AppIndNS = None
try:
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as AppIndNS  # type: ignore
except Exception:
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndNS  # type: ignore
    except Exception:
        AppIndNS = None

APP_ID = "descanso-visual"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "descanso_visual")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ui")

DEFAULTS = {
    "work_minutes": 20,
    "rest_minutes": 10,
    "show_notifications": True,
    "always_on_top": True,
}

# ----------------- Config helpers -----------------
def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)

def load_config():
    ensure_config_dir()
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULTS.copy())
        return DEFAULTS.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = DEFAULTS.copy()
        cfg.update(data or {})
        # sane bounds (asegurar ints)
        try:
            cfg["work_minutes"] = int(max(1, min(int(cfg.get("work_minutes", 20)), 240)))
        except Exception:
            cfg["work_minutes"] = DEFAULTS["work_minutes"]
        try:
            cfg["rest_minutes"] = int(max(1, min(int(cfg.get("rest_minutes", 10)), 120)))
        except Exception:
            cfg["rest_minutes"] = DEFAULTS["rest_minutes"]
        cfg["show_notifications"] = bool(cfg.get("show_notifications", True))
        cfg["always_on_top"] = bool(cfg.get("always_on_top", True))
        return cfg
    except Exception:
        return DEFAULTS.copy()

def save_config(cfg):
    ensure_config_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ----------------- ConfirmWorkWindow -----------------
class ConfirmWorkWindow(Gtk.Window):
    """Ventana que pregunta '¿Desea volver al trabajo?'"""
    def __init__(self, on_confirm, always_on_top=True):
        super().__init__(title="Volver al trabajo")
        self.set_default_size(320, 150)
        self.set_resizable(False)
        self.on_confirm = on_confirm

        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_position(Gtk.WindowPosition.CENTER)
        if always_on_top:
            self.set_keep_above(True)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(outer, f"set_margin_{side}")(20)
        self.add(outer)

        label = Gtk.Label(label="¿Desea volver al trabajo?")
        label.set_justify(Gtk.Justification.CENTER)
        label.set_halign(Gtk.Align.CENTER)

        btn_box = Gtk.Box(spacing=10)
        btn_box.set_halign(Gtk.Align.CENTER)

        btn_ok = Gtk.Button(label="Aceptar")
        btn_ok.connect("clicked", self._on_accept)

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.connect("clicked", self._on_cancel)

        btn_box.pack_start(btn_ok, False, False, 0)
        btn_box.pack_start(btn_cancel, False, False, 0)

        outer.pack_start(label, True, True, 0)
        outer.pack_start(btn_box, False, False, 0)

        self.show_all()
        GLib.idle_add(self.present)

    def _on_accept(self, _btn):
        if callable(self.on_confirm):
            self.on_confirm()
        self.destroy()

    def _on_cancel(self, _btn):
        self.destroy()

# ----------------- BreakWindow -----------------
class BreakWindow(Gtk.Window):
    """
    Ventana de descanso:
    - Muestra mensaje y cuenta regresiva.
    - Botón 'Salir del descanso' que dispara el flujo de confirmación.
    """
    def __init__(self, minutes, always_on_top=True, on_finish=None):
        super().__init__(title="Descanso visual")
        self.set_default_size(520, 220)
        self.set_resizable(False)
        self.on_finish = on_finish
        # minutos puede venir como float (modo test), convertir a segundos
        try:
            total_seconds = int(float(minutes) * 60)
        except Exception:
            total_seconds = int(minutes) * 60
        # si total_seconds == 0 (modo prueba) usar 5s
        if total_seconds <= 0:
            total_seconds = 5
        self.remaining = total_seconds
        self.tick_id = None
        self._finished = False  # para evitar doble llamada

        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_skip_taskbar_hint(False)
        self.set_skip_pager_hint(True)
        self.set_position(Gtk.WindowPosition.CENTER)
        if always_on_top:
            self.set_keep_above(True)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(outer, f"set_margin_{side}")(24)
        self.add(outer)

        title = Gtk.Label()
        title.set_markup("<span size='large' weight='bold'>Descansa tus ojos</span>")
        title.set_justify(Gtk.Justification.CENTER)
        title.set_halign(Gtk.Align.CENTER)

        self.msg = Gtk.Label(label="Mira algo a 6 metros (20 pies) y parpadea suavemente.")
        self.msg.set_halign(Gtk.Align.CENTER)
        self.msg.set_justify(Gtk.Justification.CENTER)
        self.msg.set_line_wrap(True)
        try:
            self.msg.set_line_wrap_mode(Gtk.WrapMode.WORD)
        except Exception:
            pass

        self.countdown = Gtk.Label()
        self.countdown.set_halign(Gtk.Align.CENTER)
        self.countdown.set_markup("<span size='xx-large'>00:00</span>")

        self.exit_btn = Gtk.Button(label="Salir del descanso")
        self.exit_btn.set_halign(Gtk.Align.CENTER)
        self.exit_btn.connect("clicked", self._on_exit_clicked)

        outer.pack_start(title, False, False, 0)
        outer.pack_start(self.msg, False, False, 0)
        outer.pack_start(self.countdown, True, True, 0)
        outer.pack_start(self.exit_btn, False, False, 0)

        # cuando el usuario intenta cerrar la ventana con la X -> tratar como exit
        self.connect("delete-event", self._on_delete)

        # iniciar cuenta
        self._update_countdown_label()
        self.tick_id = GLib.timeout_add_seconds(1, self._tick)
        self.show_all()
        GLib.idle_add(self.present)

    @staticmethod
    def _format_mmss(secs):
        m, s = divmod(max(0, int(secs)), 60)
        return f"{m:02d}:{s:02d}"

    def _update_countdown_label(self):
        self.countdown.set_markup(f"<span size='xx-large'>{self._format_mmss(self.remaining)}</span>")

    def _tick(self):
        # reduce y actualiza; si llega a 0, terminar descanso
        if self.remaining > 0:
            self.remaining -= 1
            self._update_countdown_label()
            return True
        # llegó a 0
        self._finish_break()
        return False

    def _on_exit_clicked(self, *_):
        # usuario forzó salida del descanso
        self._finish_break()

    def _on_delete(self, *args):
        # cerrar con la X => tratar como salir del descanso
        self._finish_break()
        return True  # evitar doble-destrucción automática por defecto

    def _finish_break(self):
        # proteger para que solo se ejecute una vez
        if self._finished:
            return
        self._finished = True

        if self.tick_id:
            try:
                GLib.source_remove(self.tick_id)
            except Exception:
                pass
            self.tick_id = None

        try:
            self.destroy()
        except Exception:
            pass

        if callable(self.on_finish):
            # Llamar al handler de la app (que abrirá la confirmación)
            try:
                self.on_finish()
            except Exception:
                pass

# ----------------- EyeCareApp -----------------
class EyeCareApp:
    def __init__(self, args):
        self.verbose = bool(getattr(args, "verbose", False))
        self.config = load_config()

        # aplicar flags CLI si existen
        if getattr(args, "work", None) is not None:
            self.config["work_minutes"] = max(1, min(int(args.work), 240))
        if getattr(args, "rest", None) is not None:
            self.config["rest_minutes"] = max(1, min(int(args.rest), 120))
        if getattr(args, "no_notify", False):
            self.config["show_notifications"] = False
        if getattr(args, "no_ontop", False):
            self.config["always_on_top"] = False
        if getattr(args, "test", False):
            # modo prueba: valores pequeños
            self.config["work_minutes"] = 0
            self.config["rest_minutes"] = 0

        # estado
        self.running = False
        self.work_tick_id = None
        self.work_remaining = 0
        self.break_window = None

        # notificaciones
        Notify.init("Descanso visual")

        # indicador en bandeja si está disponible
        self.indicator = None
        if AppIndNS:
            try:
                self.indicator = AppIndNS.Indicator.new(
                    APP_ID, "appointment-soon", AppIndNS.IndicatorCategory.APPLICATION_STATUS
                )
                # set_icon es deprecado en algunos bindings, envolver en try
                try:
                    self.indicator.set_icon("appointment-soon")
                except Exception:
                    pass
                self.indicator.set_status(AppIndNS.IndicatorStatus.ACTIVE)
                self.indicator.set_menu(self._build_menu())
            except Exception:
                self.indicator = None
                self._fallback_window()
        else:
            self._fallback_window()

        # señales
        signal.signal(signal.SIGINT, self._on_signal_exit)
        signal.signal(signal.SIGTERM, self._on_signal_exit)

        if self.verbose:
            print("[EyeCareApp] iniciado")

    # ------------ UI / menú ------------
    def _build_menu(self):
        menu = Gtk.Menu()
        self.mi_toggle = Gtk.MenuItem(label="Activar")
        self.mi_toggle.connect("activate", self.on_toggle)
        menu.append(self.mi_toggle)

        mi_force = Gtk.MenuItem(label="Forzar descanso ahora")
        mi_force.connect("activate", self.on_force_break)
        menu.append(mi_force)

        mi_config = Gtk.MenuItem(label="Configuración…")
        mi_config.connect("activate", self.on_open_config)
        menu.append(mi_config)

        mi_quit = Gtk.MenuItem(label="Salir")
        mi_quit.connect("activate", self.on_quit)
        menu.append(mi_quit)

        menu.show_all()
        return menu

    def _fallback_window(self):
        self.fallback = Gtk.Window(title="Descanso visual")
        self.fallback.set_default_size(320, 120)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.fallback.add(box)
        self.btn_toggle = Gtk.Button(label="Activar")
        self.btn_toggle.connect("clicked", lambda *_: self.on_toggle(None))
        box.pack_start(self.btn_toggle, False, False, 0)
        self.fallback.show_all()

    # ------------ acciones ------------
    def on_toggle(self, _item):
        if not self.running:
            self.start()
        else:
            self.stop()

    def on_force_break(self, _item):
        # cancelar trabajo y abrir descanso inmediatamente
        self._cancel_work_timer()
        self._show_break()

    def on_open_config(self, _item):
        try:
            cfg_win = ConfigWindow(self, UI_PATH, self.config)
            cfg_win.run()
        except Exception:
            # si falla, no rompemos la app
            pass

    def on_quit(self, _item):
        self.stop()
        Gtk.main_quit()

    # ------------ lógica timers ------------
    def start(self):
        if self.running:
            return
        self.running = True
        if hasattr(self, "mi_toggle"):
            self.mi_toggle.set_label("Detener")
        if hasattr(self, "btn_toggle"):
            self.btn_toggle.set_label("Detener")
        self._start_work_timer()
        if self.config.get("show_notifications", True):
            self._notify("Temporizador activado", f"Trabajo: {self._human_readable(self.config['work_minutes'])}")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if hasattr(self, "mi_toggle"):
            self.mi_toggle.set_label("Activar")
        if hasattr(self, "btn_toggle"):
            self.btn_toggle.set_label("Activar")
        self._cancel_work_timer()
        if self.break_window:
            try:
                self.break_window.destroy()
            except Exception:
                pass
            self.break_window = None
        if self.config.get("show_notifications", True):
            self._notify("Temporizador detenido", "")

    def _start_work_timer(self):
        self._cancel_work_timer()
        minutes = self.config.get("work_minutes", DEFAULTS["work_minutes"])
        secs = int(minutes * 60)
        if secs <= 0:
            secs = 5  # modo test
        self.work_remaining = secs
        if self.verbose:
            print(f"[Timer] Trabajo iniciado ({self.work_remaining}s)")
        self.work_tick_id = GLib.timeout_add_seconds(1, self._work_tick)

    def _cancel_work_timer(self):
        if self.work_tick_id:
            try:
                GLib.source_remove(self.work_tick_id)
            except Exception:
                pass
            self.work_tick_id = None

    def _work_tick(self):
        # retorna True para seguir, False para detener este timeout
        if not self.running:
            return False
        self.work_remaining -= 1
        if self.work_remaining > 0:
            return True
        # trabajo finalizado -> abrir descanso
        if self.verbose:
            print("[Timer] Trabajo finalizado; mostrando descanso.")
        self._show_break()
        return False

    # ------------ descanso & confirmación ------------
    def _show_break(self):
        # crear BreakWindow; cuando termine, llamará a self._break_finished
        minutes = self.config.get("rest_minutes", DEFAULTS["rest_minutes"])
        self.break_window = BreakWindow(
            minutes=minutes,
            always_on_top=self.config.get("always_on_top", True),
            on_finish=self._break_finished,
        )
        if self.config.get("show_notifications", True):
            self._notify("Tiempo de descanso", f"{int(round(minutes))} minutos")

    def _break_finished(self):
        # break_window ya fue destruida por BreakWindow._finish_break()
        self.break_window = None

        # define qué hacer si el usuario confirma volver al trabajo
        def restart_work():
            # activar y reiniciar el temporizador de trabajo
            self.running = True
            self._start_work_timer()
            if self.config.get("show_notifications", True):
                self._notify("¡Listo!", "Reiniciando ciclo de trabajo.")

        # mostrar la ventana de confirmación; si acepta, llamará a restart_work
        ConfirmWorkWindow(restart_work, always_on_top=self.config.get("always_on_top", True))

    # ------------ notificaciones ------------
    def _notify(self, title, body):
        try:
            n = Notify.Notification.new(title, body, "appointment-soon")
            n.set_timeout(3000)
            n.show()
        except Exception:
            if self.verbose:
                print(f"[Notify] {title}: {body}")

    def _on_signal_exit(self, *_):
        self.stop()
        Gtk.main_quit()

    def _human_readable(self, minutes):
        if minutes <= 0:
            return "modo prueba"
        return f"{minutes} min"

# ----------------- ConfigWindow (usa tu config.ui) -----------------
class ConfigWindow:
    """
    Ventana de Configuración cargada desde GtkBuilder (.ui).
    Debe existir config.ui en la misma carpeta (tu archivo actual).
    """
    def __init__(self, parent_app, ui_path, cfg):
        self.app = parent_app
        if not os.path.exists(ui_path):
            self._error_dialog("No se encontró el archivo UI", f"No existe: {ui_path}")
            self.window = None
            return

        self.builder = Gtk.Builder.new_from_file(ui_path)
        self.window: Gtk.Window = self.builder.get_object("config_window")
        self.window.set_modal(False)
        self.window.set_position(Gtk.WindowPosition.CENTER)

        # Widgets por ids que ya tienes en tu UI
        self.spin_work: Gtk.SpinButton = self.builder.get_object("spin_work")
        self.spin_rest: Gtk.SpinButton = self.builder.get_object("spin_rest")
        self.sw_notify: Gtk.Switch = self.builder.get_object("switch_notify")
        self.sw_on_top: Gtk.Switch = self.builder.get_object("switch_on_top")
        self.btn_cancel: Gtk.Button = self.builder.get_object("btn_cancel")
        self.btn_save: Gtk.Button = self.builder.get_object("btn_save")

        # Valores iniciales
        self.spin_work.set_value(cfg["work_minutes"])
        self.spin_rest.set_value(cfg["rest_minutes"])
        self.sw_notify.set_active(cfg["show_notifications"])
        self.sw_on_top.set_active(cfg["always_on_top"])

        # Señales
        self.btn_cancel.connect("clicked", self._on_cancel)
        self.btn_save.connect("clicked", self._on_save)
        self.window.connect("delete-event", self._on_cancel)

    def run(self):
        if self.window:
            self.window.show_all()

    def _on_cancel(self, *a):
        if self.window:
            self.window.destroy()
        return True

    def _on_save(self, _btn):
        work = max(1, min(self.spin_work.get_value_as_int(), 240))
        rest = max(1, min(self.spin_rest.get_value_as_int(), 120))

        self.app.config["work_minutes"] = work
        self.app.config["rest_minutes"] = rest
        self.app.config["show_notifications"] = bool(self.sw_notify.get_active())
        self.app.config["always_on_top"] = bool(self.sw_on_top.get_active())

        save_config(self.app.config)

        if self.app.running:
            # si ya estaba corriendo, reiniciar con los nuevos valores
            self.app._start_work_timer()
            if self.app.config.get("show_notifications", True):
                self.app._notify("Configuración guardada", "Se reinició el ciclo de trabajo.")

        if self.window:
            self.window.destroy()

    def _error_dialog(self, title, body):
        dlg = Gtk.MessageDialog(
            transient_for=None,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
        )
        dlg.format_secondary_text(body)
        dlg.run()
        dlg.destroy()

# ----------------- CLI -----------------
def parse_args():
    p = argparse.ArgumentParser(description="Descanso visual – temporizador trabajo/descanso")
    p.add_argument("--test", action="store_true", help="Modo prueba rápida (trabajo y descanso cortos)")
    p.add_argument("--work", type=int, help="Minutos de trabajo (1–240)")
    p.add_argument("--rest", type=int, help="Minutos de descanso (1–120)")
    p.add_argument("--no-notify", action="store_true", help="Desactivar notificaciones")
    p.add_argument("--no-ontop", action="store_true", help="Desactivar 'siempre visible'")
    p.add_argument("--verbose", action="store_true", help="Mensajes de depuración")
    return p.parse_args()

# ----------------- main -----------------
def main():
    args = parse_args()
    app = EyeCareApp(args)
    Gtk.main()

if __name__ == "__main__":
    main()
