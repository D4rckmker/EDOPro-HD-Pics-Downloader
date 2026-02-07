# <img src="https://projectignis.github.io/assets/img/ignis_logo.png" width="80"/> Armytille's EDOPro HD Pics Downloader

[![PowerShell Version](https://img.shields.io/badge/PowerShell-5.1%2B-blue)](https://docs.microsoft.com/en-us/powershell/scripting/overview)  
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)  

[Read in English](README.md)

[¿Quieres una alternativa para macOS, Windows y Linux?](OPTIONS_ES.md)

**Armytille’s EDOPro HD Pics Downloader** es una **aplicación GUI de PowerShell** que permite descargar fácilmente **imágenes HD de cartas de Yu‑Gi‑Oh!** para **EDOPro**.

---

## 🌟 Características

- Descarga **todas las cartas de Yu‑Gi‑Oh! en HD**.
- Manejo especial de **imágenes recortadas de Magias de Campo**.
- Soporte automático para **artes alternativos**.
- Opción para **forzar sobrescritura** de imágenes existentes.
- **Barra de progreso en tiempo real** y **registro (log)**.
- **GUI simple** con Windows Forms.
- **Manejo de errores y reintentos** automático.

---

## ⚡ Instalación y uso

1. **Descarga el script** `EDOPro-HD-Pics-Downloader.ps1`.
2. **Coloca el archivo** en la **raíz de tu carpeta de EDOPro**, en el mismo nivel que la carpeta `pics`.  
3. **Ejecuta el script**: **clic derecho → Run with PowerShell**.

4. **Uso de la GUI**:

- Haz clic en **“Download All Cards”** para iniciar la descarga.
- Marca **“Force Overwrite Existing”** para sobrescribir imágenes.
- Haz clic en **“Cancel”** para detener la descarga en cualquier momento.
- La **barra de progreso** y el **log** muestran el estado en tiempo real.
  
<img width="616" height="261" alt="image" src="https://github.com/user-attachments/assets/69c0684e-5961-4e64-a503-192aede20b93" />

---

*(Opcional)* Habilita la ejecución sin restricciones en PowerShell si es necesario (como Admin):
```powershell
Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope CurrentUser
```
