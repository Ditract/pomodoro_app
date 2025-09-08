# views.py
import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

# Ventana que pregunta si volver al trabajo
class ConfirmWorkWindow(Gtk.Window):
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
            try:
                self.on_confirm()
            except Exception:
                pass
        self.destroy()

    def _on_cancel(self, _btn):
        self.destroy()


# Ventana de descanso con contador y botón "Salir del descanso"
class BreakWindow(Gtk.Window):
    def __init__(self, minutes, always_on_top=True, on_finish=None):
        super().__init__(title="Descanso visual")
        self.set_default_size(520, 220)
        self.set_resizable(False)
        self.on_finish = on_finish

        # minutos puede venir como float (modo test)
        try:
            total_seconds = int(float(minutes) * 60)
        except Exception:
            total_seconds = int(minutes) * 60
        if total_seconds <= 0:
            total_seconds = 5  # modo test si guardaron 0

        self.remaining = total_seconds
        self.tick_id = None
        self._finished = False

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

        # cerrar con X -> tratar como exit
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
        if self.remaining > 0:
            self.remaining -= 1
            self._update_countdown_label()
            return True
        # llegó a 0 -> terminar descanso
        self._finish_break()
        return False

    def _on_exit_clicked(self, *_):
        self._finish_break()

    def _on_delete(self, *args):
        # tratar la X como "salir del descanso"
        self._finish_break()
        return True  # evitar doble-destrucción automática por defecto

    def _finish_break(self):
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
            try:
                self.on_finish()
            except Exception:
                pass


# ConfigWindow: carga desde config.ui (usa ids: spin_work, spin_rest, switch_notify, switch_on_top, btn_cancel, btn_save)
class ConfigWindow:
    def __init__(self, parent_app, ui_path, cfg):
        self.app = parent_app
        if not os.path.exists(ui_path):
            self.window = None
            return

        self.builder = Gtk.Builder.new_from_file(ui_path)
        self.window = self.builder.get_object("config_window")

        # centrar
        if self.app and hasattr(self.app, "main_window") and self.app.main_window:
            self.window.set_transient_for(self.app.main_window)
            self.window.set_modal(True)
            self.window.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        else:
            self.window.set_position(Gtk.WindowPosition.CENTER)

        # Widgets
        self.spin_work = self.builder.get_object("spin_work")
        self.spin_rest = self.builder.get_object("spin_rest")
        self.sw_notify = self.builder.get_object("switch_notify")
        self.sw_on_top = self.builder.get_object("switch_on_top")
        self.btn_cancel = self.builder.get_object("btn_cancel")
        self.btn_save = self.builder.get_object("btn_save")

        # Inicializar valores
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
        # Guardar en el app parent (controlador)
        work = max(1, min(self.spin_work.get_value_as_int(), 240))
        rest = max(1, min(self.spin_rest.get_value_as_int(), 120))
        self.app.config["work_minutes"] = work
        self.app.config["rest_minutes"] = rest
        self.app.config["show_notifications"] = bool(self.sw_notify.get_active())
        self.app.config["always_on_top"] = bool(self.sw_on_top.get_active())

        # persistir con settings (import aquí para evitar dependencia circular al top)
        try:
            from settings import save_config
            save_config(self.app.config)
        except Exception:
            pass

        # Si está corriendo, adoptar cambios en caliente
        if self.app.running:
            self.app._start_work_timer()
            if self.app.config.get("show_notifications", True):
                self.app._notify("Configuración guardada", "Se reinició el ciclo de trabajo.")

        if self.window:
            self.window.destroy()
