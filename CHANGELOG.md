# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Programas: Se crearon los programas principales del proyecto.(observerclient, singletonclient, singletonproxyobserver,etc).
- Tests: Se crearon casos de test para validar el funcionamiento del sistema.(test_observerclient.py, test_singletonclient.py, test_singletonproxyobserver.py, etc).
- Documentación: Se creó la guía de ejecución (`Guia_ejecucion.md`) para facilitar el uso del sistema.
- Flujo completo: Se implementó el flujo completo de procesar archivos JSON, validando el schema, aplicando transformaciones y guardando resultados en AWS S3.
- Testing: Se añadieron casos de test para validar el funcionamiento del sistema.
- Tests: Se agregaron casos de tests para cumplir una cobertura mayor a 85%.

### Changed

- Documentación: Se modificó la guía de ejecución (`Guia_ejecucion.md`) para facilitar el uso del sistema. Se agregaron ejemplos de uso de los programas y casos de prueba, como tambien las pruebas de integration.

### Removed
- Se eliminaron los archivos `main.py` y `main2.py` ya que no se utilizan en el sistema.
- Se eliminaron los archivos `test_main.py` y `test_main2.py` ya que no se utilizan en el sistema.
- Se elimino la carpeta credenciales

### Fixed
- Se corrigio el error de importacion en el archivo observerclient.py
- Se corrigieron los archivos de test para que cumplan con el estandar de pytest
- Se corrigieron los programas para que cumplan con el formato brindado por black
- Se corrigieron los archivos para  que cumplan el estandar PEP8 y PEP257


