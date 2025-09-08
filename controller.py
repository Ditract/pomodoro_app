# controller.py
import os
import signal
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gtk, GLib, Notify

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

from settings import load_config
from views import BreakWindow, ConfirmWorkWindow, ConfigWindow

APP_ID = "descanso-visual"


class EyeCareController:
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
            # modo prueba: valores pequeños (guardados como 0 => tratados abajo)
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

        # signals for clean exit
        signal.signal(signal.SIGINT, self._on_signal_exit)
        signal.signal(signal.SIGTERM, self._on_signal_exit)

        if self.verbose:
            print("[EyeCareController] iniciado")

    # ----------------- menú / fallback -----------------
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
        # ventana simple para entornos sin bandeja
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

    # ----------------- acciones -----------------
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
            cfg_win = ConfigWindow(self, os.path.join(os.path.dirname(__file__), "config.ui"), self.config)
            cfg_win.run()
        except Exception:
            pass

    def on_quit(self, _item):
        self.stop()
        Gtk.main_quit()

    # ----------------- timers / ciclo -----------------
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
        minutes = self.config.get("work_minutes", 20)
        secs = int(minutes * 60)
        # modo test: si guardaron 0 (flag --test), usar 5s
        if secs <= 0:
            secs = 5
        self.work_remaining = secs
        if self.verbose:
            print(f"[Timer] Trabajo iniciado ({self.work_remaining}s)")
        self.work_tick_id = GLib.timeout_add_seconds(1, self._work_tick)

    def _cancel_work_timer(self):
        if getattr(self, "work_tick_id", None):
            try:
                GLib.source_remove(self.work_tick_id)
            except Exception:
                pass
            self.work_tick_id = None

    def _work_tick(self):
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

    # ----------------- descanso & confirmación -----------------
    def _show_break(self):
        minutes = self.config.get("rest_minutes", 10)
        # crear BreakWindow; cuando termine, llamará a self._break_finished
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

        def restart_work():
            self.running = True
            self._start_work_timer()
            if self.config.get("show_notifications", True):
                self._notify("¡Listo!", "Reiniciando ciclo de trabajo.")

        # mostrar confirmación; si acepta, restart_work()
        ConfirmWorkWindow(restart_work, always_on_top=self.config.get("always_on_top", True))

    # ----------------- notificaciones -----------------
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
