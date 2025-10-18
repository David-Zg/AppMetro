#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script simple para crear el archivo de credenciales de usuario (user_credentials.json)
compatible con la clase SecurityManager del paquete `cert_app`.

Uso:
  - Generar token de activación para un identificador (administrador):
      python create_credentials.py --generate-token --id CLIENTE-001

  - Crear credenciales (valida token):
      python create_credentials.py --id CLIENTE-001 --username operador

  - Forzar creación sin verificar token (peligroso):
      python create_credentials.py --id CLIENTE-001 --username operador --force

El script reutiliza la clase SecurityManager para generar/verificar token y hashear
las contraseñas correctamente.
"""

import argparse
import getpass
import sys
from cert_app.security import SecurityManager


def main():
    parser = argparse.ArgumentParser(description="Crear credenciales de usuario para la aplicación")
    parser.add_argument('--generate-token', action='store_true', help='Generar token de activación para un identificador')
    parser.add_argument('--id', dest='identifier', help='Identificador de instalación (p.ej. CLIENTE-001)')
    parser.add_argument('--username', help='Nombre de usuario a crear')
    parser.add_argument('--force', action='store_true', help='Crear credenciales sin verificar token (no recomendado)')
    args = parser.parse_args()

    sm = SecurityManager()

    if args.generate_token:
        if not args.identifier:
            print('Debe indicar --id IDENTIFICADOR para generar el token')
            sys.exit(1)
        token = sm.generate_init_token_for_id(args.identifier)
        print(f'Token de activación para "{args.identifier}":\n\n{token}\n')
        print('Entrega este token al instalador/administrador; el instalador deberá introducirlo para activar el sistema.')
        return

    # Crear credenciales
    if not args.identifier:
        args.identifier = input('Identificador de instalación (p.ej. CLIENTE-001): ').strip()
        if not args.identifier:
            print('Identificador requerido. Saliendo.')
            sys.exit(1)

    if not args.username:
        args.username = input('Usuario (ej: operador): ').strip()
        if not args.username:
            print('Usuario requerido. Saliendo.')
            sys.exit(1)

    # Si ya existen credenciales, confirmar sobreescritura
    if sm.credentials_exist():
        print('Ya existe un archivo de credenciales para esta instalación.')
        if not args.force:
            resp = input('¿Desea sobrescribir las credenciales existentes? (s/N): ').strip().lower()
            if resp != 's':
                print('Operación cancelada. No se modificaron credenciales.')
                return

    # Verificar token a menos que se use --force
    if not args.force:
        token_input = getpass.getpass('Token de activación: ')
        if not sm.verify_init_token(args.identifier.strip(), token_input.strip()):
            print('Token inválido. Si creaste el token con --generate-token asegúrate de usar el mismo identificador y token.')
            sys.exit(2)

    # Pedir contraseña de usuario
    while True:
        pwd1 = getpass.getpass('Contraseña de usuario: ')
        if not pwd1:
            print('Contraseña vacía. Intente nuevamente.')
            continue
        pwd2 = getpass.getpass('Confirmar contraseña: ')
        if pwd1 != pwd2:
            print('Las contraseñas no coinciden. Intente nuevamente.')
            continue
        if len(pwd1) < 6:
            print('Contraseña demasiado corta (mínimo 6 caracteres).')
            continue
        break

    # Pedir contraseña maestra
    while True:
        master1 = getpass.getpass('Contraseña maestra: ')
        if not master1:
            print('Contraseña maestra vacía. Intente nuevamente.')
            continue
        master2 = getpass.getpass('Confirmar contraseña maestra: ')
        if master1 != master2:
            print('Las contraseñas maestras no coinciden. Intente nuevamente.')
            continue
        if len(master1) < 6:
            print('Contraseña maestra demasiado corta (mínimo 6 caracteres).')
            continue
        break

    data = {
        'install_id': args.identifier.strip(),
        'created_at': __import__('time').time(),
        'user': {
            'username': args.username.strip(),
            'password': sm.hash_password(pwd1)
        },
        'master': sm.hash_password(master1)
    }

    sm.save_credentials(data)
    print('\nCredenciales creadas correctamente en el archivo de usuario dentro del paquete cert_app.')


if __name__ == '__main__':
    main()
