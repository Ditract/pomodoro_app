#!/bin/bash

# Verificar que Python3 esté instalado
if ! command -v python3 &> /dev/null
then
    echo "Python3 no está instalado. Por favor instálalo primero."
    exit 1
fi

# Ejecutar la app
python3 main.py

