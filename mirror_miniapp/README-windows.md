# Tobyworld Mirror Mini App — Windows Guide

A lightweight Tobyworld knowledge app packaged for Windows.  
Requires **LM Studio** running locally to serve the AI model.

---

## 1. Install LM Studio
- Download from: [https://lmstudio.ai](https://lmstudio.ai)
- Install and launch LM Studio.
- Go to **Local Server** → Enable API Server (default: `http://localhost:1234`).
- Load **any AI model of your choice** in LM Studio  
  *(Recommended: Tobyworld Mirror AI model for full lore experience)*.

---

## 2. Install Tobyworld Mirror
- Download → [**Windows_Tobyworld Mirror 1.0.0.0.zip**](https://drive.google.com/file/d/1mA7_YvpJMGpXySZY-O_0Ad8Ot50kfypA/view?usp=drive_link)
- Extract the `.zip` file.
- Run `Setup_Tobyworld Mirror_1.0.0.0.exe` and follow the installer steps.


---

## 3. Load the Lore Scrolls (Required)
After installation, you need to load the **lore scrolls** into the app’s data folder:

1. Locate the installation folder:
   ```
   C:\Tobyworld Mirror\lore-scrolls
   ```
2. Copy all your `*.md` lore scroll files into this folder.
3. Restart **Tobyworld Mirror** so it can load the scrolls.

Without these scrolls, the Mirror will not have the full Tobyworld knowledge base.

---

## 4. Configure & Run
1. Launch **Tobyworld Mirror** after installation.
2. Open **Settings**.
3. Set API URL to:  
   ```
   http://127.0.0.1:1234/v1
   ```
4. Save and start chatting with the Mirror.

---

## 5. Notes
- LM Studio must be running before launching Tobyworld Mirror.
- You may load **any compatible AI model** in LM Studio — it does not have to be Tobyworld-specific.
- If the API port changes in LM Studio, update it in the Mirror settings.

---

## 📜 License
MIT License © 2025 ToadAid
