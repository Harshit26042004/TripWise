# 🧭 Trip Wise – AI-Powered Trip Organizing Application

Trip Wise is a smart, AI-powered travel planning assistant that helps users plan their trips effortlessly. It organizes itineraries, suggests destinations, compares flights and hotels, and manages budgets through an intuitive desktop application.  
Built with **Python**, packaged for **Windows**, and powered by **Google APIs** + **Amadeus API** for real-time travel data.

---

## 📂 Project Structure
```
TripWise/
│
├─ assets/ # App icons, UI assets
├─ img/ # Writeup & preview images
├─ src/
│ ├─ app.py # Main application logic
│ ├─ build_exe.py # Script used to build Windows executable
│
├─ windows/
│ └─ TripWise.exe # Pre-built Windows application
│
├─ requirements.txt # Required dependencies
└─ README.md
```


---

## 🔑 Setting Up API Credentials

Trip Wise requires **Google API** and **Amadeus API** credentials.  

Copy and paste the following template into a json file:

```json
{
    "GOOGLE_API": "XXXXXXXXXXXXXXXXXX",
    "Amadeus_KEY": "****************",
    "Amadeus_SECRET": "YYYYYYYYY"
}
```
Replace the placeholder values with your actual credentials.

## 🚀 How to Run the Application
Option 1: Run the Pre-Built Windows Executable
Open the windows/ folder.

Double-click:

```
TripWise.exe
```
Locate the credentials.json and upload in application

Option 2: Run From Source
1. Create a virtual environment (recommended)
```bash
python -m venv venv
Activate it:
```

- Mac/Linux

```bash
source venv/bin/activate
```
- Windows
```bash
venv\Scripts\activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Ensure credentials.json exists in the project root
4. Run the app
```bash
python src/app.py
```

---
## 🏗️ Building the Windows Executable
If you want to build your own EXE:

```bash
python src/build_exe.py
```
This will package the app into a Windows-compatible executable.

## ✨ Key Features
- 🧭 Smart itinerary generation

- ✈️ Flight + hotel suggestions using Amadeus API

- 🗺️ Destination recommendations

- 🗓️ Daily trip planning

- 💰 Budget tracking & optimizations

- 🤖 AI-powered travel insights using Google APIs

- 🪟 Desktop-ready EXE application for Windows

## 📸 Preview
All project screenshots, diagrams, and write-up images are available in the img/ folder.


