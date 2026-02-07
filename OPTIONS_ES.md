# EDOPro HD Pics Downloader — Opciones y uso con Python

[Read in English](OPTIONS.md)

[¿No tienes Python instalado?](PYTHON_INSTALL_ES.md)

## Uso rápido (Python)
1. Ejecuta el script con Python y espera a que detecte `pics`.
2. Si no detecta, selecciona la ruta manualmente.
3. (Opcional) Ajusta las opciones.
4. Pulsa **Iniciar**.

## Opciones
- **Carpeta pics**: ruta exacta a `pics` de ProjectIgnis/EDOPro.
- **Forzar reemplazo**: vuelve a descargar todo.
- **Solo faltantes**: descarga solo archivos que no estén.
- **Validar existentes**: re‑descarga imágenes corruptas.
- **Concurrencia**: descargas en paralelo.
- **Reintentos**: intentos por imagen.
- **Timeout (s)**: tiempo máximo por imagen.
- **Máx KB/s**: límite por descarga (0 = sin límite).
- **Filtro tipo**: filtra por tipo (ej. `Spell`, `Monster`, `Trap`).
- **Filtro set**: filtra por set/código (ej. `LOB (Legend of Blue Eyes White Dragon)`, `SDY (Starter Deck: Yugi)`).

## Botones
- **Vista previa**: muestra cuántas imágenes se descargarán.
- **Iniciar**: comienza la descarga.
- **Pausar/Reanudar**: pausa sin cancelar.
- **Cancelar**: detiene la descarga.

## Reportes
Se guardan junto al script en `reports-reportes/`:
- `edopro_download_report_YYYYMMDD_HHMMSS.json`
- `edopro_download_report_YYYYMMDD_HHMMSS.md`
