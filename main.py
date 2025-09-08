# main.py
import argparse
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gtk

from controller import EyeCareController


def parse_args():
    p = argparse.ArgumentParser(description="Descanso visual – temporizador trabajo/descanso")
    p.add_argument("--test", action="store_true", help="Modo prueba rápida (trabajo y descanso cortos)")
    p.add_argument("--work", type=int, help="Minutos de trabajo (1–240)")
    p.add_argument("--rest", type=int, help="Minutos de descanso (1–120)")
    p.add_argument("--no-notify", action="store_true", help="Desactivar notificaciones")
    p.add_argument("--no-ontop", action="store_true", help="Desactivar 'siempre visible'")
    p.add_argument("--verbose", action="store_true", help="Mensajes de depuración")
    return p.parse_args()


def main():
    args = parse_args()
    app = EyeCareController(args)
    # No arrancamos automáticamente: el comportamiento es igual al anterior (el usuario activa desde el menú).
    # Si quieres auto-start en pruebas, descomenta la siguiente línea:
    # if args.test: app.start()
    Gtk.main()


if __name__ == "__main__":
    main()
