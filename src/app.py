import flet as ft
import tempfile
import os
import webbrowser
import json
from typing import Dict, List
import uuid
import requests
from datetime import datetime
from google.genai import types

from google.adk.agents import Agent, LlmAgent, ParallelAgent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search, AgentTool

# Global state
credentials: Dict[str, str] = {}
html_list: List[str] = []  # This will store all generated HTMLs in order

global GOOGLE_API_KEY
global AMADEUS_CLIENT_ID
global AMADEUS_CLIENT_SECRET

#   ========================= Custom Tools Functions =========================

def _get_token():
    
    AMADEUS_CLIENT_ID = credentials["Amadeus_KEY"]           # often called client_id in Amadeus
    AMADEUS_CLIENT_SECRET = credentials["Amadeus_SECRET"]

    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET
    }
  
    r = requests.post(url, data=data, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

def _iata_lookup(city: str) -> str:
    """Convert city name → IATA code (city-level preferred)"""
    if not city or len(city.strip()) < 2:
        return city[:3].upper()

    city = city.strip()
    try:
        token = _get_token()
        url = "https://test.api.amadeus.com/v1/reference-data/locations"
        params = {
            "keyword": city,
            "subType": "CITY,AIRPORT",
            "view": "LIGHT"
        }
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])

        if not data:
            print(f"[IATA Lookup] No results for '{city}'")
            return city[:3].upper()

        # Prefer CITY over AIRPORT
        for loc in data:
            if loc.get("subType") == "CITY":
                iata = loc["iataCode"]
                print(f"[IATA Lookup] {city} → {iata} (CITY)")
                return iata
        # Fallback to first airport
        iata = data[0]["iataCode"]
        print(f"[IATA Lookup] {city} → {iata} (AIRPORT)")
        return iata

    except Exception as e:
        print(f"[IATA Lookup] Error for '{city}': {e}")
        return city[:3].upper()

def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 1,
    return_date: str = "",
    currency: str = "INR",
    max_results: int = 3
) -> list:
    try:
        origin_code = _iata_lookup(origin)
        dest_code = _iata_lookup(destination)

        if len(origin_code) != 3 or len(dest_code) != 3:
          return [{"error": f"Invalid IATA: origin='{origin_code}', dest='{dest_code}'"}]

        token = _get_token()
        url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        params = {
            "originLocationCode": origin_code,
            "destinationLocationCode": dest_code,
            "departureDate": departure_date,
            "adults": adults,
            "currencyCode": currency,
            "max": max_results * 2
        }
        if return_date:
            params["returnDate"] = return_date

        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15)
        if r.status_code != 200:
            return [{"error": f"API {r.status_code}: {r.text[:100]}"}]

        offers = r.json().get("data", [])[:max_results]
        results = []
        for o in offers:
            seg = o["itineraries"][0]["segments"]
            results.append({
                "price": f"{o['price']['currency']} {o['price']['total']}",
                "airline": seg[0]["carrierCode"],
                "departure": seg[0]["departure"]["iataCode"],
                "arrival": seg[-1]["arrival"]["iataCode"],
                "dep_time": seg[0]["departure"]["at"][11:16],
                "arr_time": seg[-1]["arrival"]["at"][11:16],
                "stops": len(seg) - 1
            })
        print(f"[Flight Search] Found {len(results)} offers from {origin_code} to {dest_code}")
        return results or [{"info": "No flights found"}]
    except Exception as e:
        return [{"error": str(e)}]

#   ========================== Agent Setup ==========================

coordinator = Agent(
    name = "CoordinatorAgent",
    description = "Agent that fetches informations like origin, destination, days of stay, Budget and other preferences.",
    model = Gemini(model="gemini-2.5-flash-lite"),
    instruction = """You are a tourist expert and provide an experienced guidance for making a trip for below mentioned details if available else asks for valid details clearly.

    User will provide a sentence with their required trip details, you should fetch the required information from the sentence like origin, destination, days of stay, Budget, start_date, end_date and other preferences. Use this fetched details for further processing.
    return a dictionary of
    - origin (str)
    - destination (str)
    - days_of_stay (int)
    - budget (float)
    - departure_date (str)
    - return_date (str)
    - other_preferences (str)
    """,
    output_key = "trip_details",
)

planes = Agent(
    name = "FlightAgent",
    description = "This Agent get the flights in the trip",
    model = Gemini(model="gemini-2.5-flash-lite"),
    instruction = """You are a flight booking agent. The origin, destination, start_date(which is departure_date) and other details are mentioned in {trip_details} .
    1. If they mentioned number of adults in preference mention it otherwise let it be 2 or 4
    2. You need to use the `search_flights` tool to get the flight details.
    3. Summarize the budget friendly flights available in short with their details
    3. Return the flight list in dictionary format for further use.

    Note: You are not allowed to generate content other than the flight list.  You are not allowed to talk unnecessarily, just provide details.
    """,
    output_key = "flights",
    tools = [search_flights],
)

activities = Agent(
    name = "ActivityAgent",
    description = "This Agent get the activities to happen in the trip",
    model = Gemini(model="gemini-2.5-flash-lite"),
    instruction = """You are a tourist guide in the destination place mentioned in {trip_details}
    For no of days mentioned above create activities to be performed each day, tell by morning, afternoon and evening activities based on the preference mentioned.
    Try to make the activities stays within the budget mentioned. Provide each day activities in a time chart order.
    1. Use `google_search` tool to get the activities list.
    2. Select the activities from the activities list filtered by budget and preference mentioned in trip details.
    3. You should Make a short time line like activities list for each day split by morning, afternoon and evening.
    4. Return the activities list in dictionary format for further use.

    Note: You should provide a basic roadmap for the activities to be performed. You are not allowed to talk unnecessarily, just provide details.
    """,
    output_key = "activities",
    tools = [google_search],
)

parallel_agent = ParallelAgent(
    name = "ParallelAgent",
    description = "This Agent get the flights, hotels and activities in the trip",
    sub_agents= [planes, activities]
)

collaborate = Agent(
    name = "CollabAgent",
    description = "This Agent combines all the parallel results and provide suitable trip plan.",
    model = Gemini(model="gemini-2.5-flash-lite"),
    instruction = """You are a tourist guide and a financial expert.
    1. Select best low price flight ticket from the list mentioned in {flights} and mention it.
    2. Select all activities from the list mentioned in {activities} that fits within the budget. Provide a table like with each day activities.
    3. Use all selected details from above and provide budget tips, accessory tips (like raincoat, selfie stick, powerbank, hiking shoes) and cost breakdown

    Note: You are a friendly ReadMe generator.Avoid commanded message response and share a warm content with the user.You should provide estimated cost at the end.
    """,
    output_key = "trip_plan",
)

webview = Agent(
    name = "WebView",
    description = "This Agent generates a Interactive frontend with trip details",
    model = Gemini(model="gemini-2.5-flash-lite"),
    instruction = """You are a fullstack developer and expert in making single HTML file with interative designs in it. The trip details are available as readme format in {trip_plan}, use those contents to generate a beautiful HTML page for Trip to provided destination. Use suitable elements for suitable contents like H2 for Trip heading, bullet points list for Guides and tips, table for expense breakdown, etc.
    Instruction: Use CSS, javacript inline for single file generation. create a colourful combo's and design.
    Note: If possible use Bootstrap and tailwind like frameworks for more interative designs like timeline slider for daily activities table. Try to make it more interactive and responsive.
    Note: You are not allowed to talk unnecessarily, just provide details in HTML format.
    """,
    output_key = "webview",
)

ui_agent = Agent(
    name = "ui_agents",
    description = "This Agent generates a enhanced frontend with trip details",
    model = Gemini(model="gemini-2.5-flash-lite"),
    instruction = """You are a frontend expert in making single HTML file with responsive interative designs in it.
    Use the {webview} and update the elements with more interactive and responsive designs. You are allowed to use tailwind, bootstrap and other frameworks that enhance the design. Enhance the UI/UX with different frameworks. update the basic html elements with framework elements which provides better interation and responsive and more attractive website. Create this within single HTML file. Try to avoid errors, bugs in generation.
    Instruction: Use CSS, javacript inline for single file generation. create a colourful combo's and design.
    Note: You are not allowed to talk unnecessarily, just provide details in HTML format.
    Note: Remove copyright texts, copyright years  if any available in the HTML code.
    """,
    output_key = "ui_view",
)

optm = Agent(
    name = "optimizer",
    description = "This Agent rectifies errors in code and optimizes it.",
    model = Gemini(model="gemini-2.5-flash-lite"),
    instruction = """You are a frontend expert in making single HTML file with responsive interative designs in it.
    Use the {ui_view} and check for any bugs, errors, fixes. Try to fix them and solve the problems available in the HTML code. Try to optimize the code to run neatly in single file format itself.return the errorless code in HTML format.
    Instruction: Use CSS, javacript inline for single file generation. create a colourful combo's and design.
    Note: You are not allowed to talk unnecessarily, just provide details in HTML code in a string format, dont mention ```html ``` or any other texts.
    Note: Remove copyright texts, copyright years  if any available in the HTML code.
    """,
    output_key = "final_ui",
)

root_agent = SequentialAgent(
    name="rootAgent",
    description="Used to create a trip plan",
    sub_agents=[coordinator, parallel_agent, collaborate, webview, ui_agent, optm],
)

session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name="Test App", session_service=session_service)

#  ============================= Main application =============================

def main(page: ft.Page):
    page.title = "TripWise – AI Travel Assistant"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1300
    page.window_height = 850
    page.window_resizable = True
    page.padding = 20

    # ====================== FILE PICKER ======================
    def load_credentials(e: ft.FilePickerResultEvent):
        if not e.files:
            page.snack_bar = ft.SnackBar(ft.Text("No file selected"))
            page.snack_bar.open = True
            page.update()
            return

        file = e.files[0]
        try:
            with open(file.path, "r", encoding="utf-8") as f:
                data = json.load(f)

            required = ["GOOGLE_API", "Amadeus_KEY", "Amadeus_SECRET"]
            if not all(k in data for k in required):
                page.snack_bar = ft.SnackBar(ft.Text("Missing keys!"))
                page.snack_bar.open = True
                page.update()
                return

            global credentials
            credentials = data

            GOOGLE_API_KEY = data["GOOGLE_API"]
            AMADEUS_CLIENT_ID = data["Amadeus_KEY"]           # often called client_id in Amadeus
            AMADEUS_CLIENT_SECRET = data["Amadeus_SECRET"]
            print("\n \n[Credentials] Loaded successfully.\n\n")

            os.environ["GEMINI_API_KEY"] = GOOGLE_API_KEY

            credential_card.visible = False
            main_ui.visible = True

            page.snack_bar = ft.SnackBar(ft.Text("Ready! Ask me anything"), bgcolor=ft.Colors.GREEN_700)
            page.snack_bar.open = True
            page.update()

        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"))
            page.snack_bar.open = True
            page.update()

    file_picker = ft.FilePicker(on_result=load_credentials)
    page.overlay.append(file_picker)

    # ====================== CREDENTIAL CARD ======================
    credential_card = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.SHIELD_OUTLINED, size=80, color=ft.Colors.GREEN_400),
            ft.Text("TripWise Setup", size=28, weight=ft.FontWeight.BOLD),
            ft.Text("Secure credentials required to continue", text_align="center"),
            ft.Text("You need a credentials.json file with:", size=13, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Container(
                ft.Text("• GOOGLE_API\n• Amadeus_KEY\n• Amadeus_SECRET", size=12),
                bgcolor=ft.Colors.INDIGO_500,
                padding=15,
                border_radius=10,
            ),
            ft.ElevatedButton(
                "Load credentials.json",
                icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE),
                height=50,
                on_click=lambda _: file_picker.pick_files(allowed_extensions=["json"]),
            ),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15),
        width=400,
        padding=20,
        bgcolor=ft.Colors.SURFACE,
        border_radius=20,
        shadow=ft.BoxShadow(blur_radius=20),
        alignment=ft.alignment.center,
    )

    # ====================== CHAT HISTORY ======================
    chat_history = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

    # ====================== INPUT BAR (bottom fixed) ======================
    chat_input = ft.TextField(
        hint_text="Where do you want to go? (e.g. Paris in December)",
        expand=True,
        autofocus=True,
        border_radius=30,
        bgcolor=ft.Colors.DEEP_PURPLE_300,
        color=ft.Colors.BLACK,
        hint_style=ft.TextStyle(
            color=ft.Colors.BLACK,        # Your desired hint color
        ),
    )

    def send_message(e):
        query = chat_input.value.strip()
        if not query:
            return

        # Add user message
        chat_history.controls.append(
            ft.Container(
                ft.Text(query, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.BLUE_700,
                padding=15,
                border_radius=20,
                margin=ft.margin.only(right=80, bottom=10),
                alignment=ft.alignment.center_right,
            )
        )

        chat_input.value = ""
        page.update()

        # Generate plan and add new button
        page.run_task(process_personal_function, query)

    input_bar = ft.Container(
        ft.Row([
            chat_input,
            ft.IconButton(ft.Icons.SEND_ROUNDED, icon_color=ft.Colors.WHITE, on_click=send_message)
        ], vertical_alignment="center"),
        padding=10,
        bgcolor=ft.Colors.DEEP_PURPLE_400,
        border_radius=30,
        margin=ft.margin.only(top=10),
    )

    # ====================== MAIN UI (with fixed input at bottom) ======================
    main_ui = ft.Column([
        ft.Container(ft.Text("TripWise AI", size=40, weight=ft.FontWeight.BOLD), padding=15, alignment=ft.alignment.center),
        ft.Divider(),
        ft.Container(chat_history, expand=True),  # Chat history takes all space
        input_bar,  # Always at bottom
    ], expand=True, visible=False)

    # ====================== PROCESS QUERY & ADD BUTTON ======================
    async def run_agent(query: str, runner: Runner) -> str:
        
        response = await runner.run_debug(
            query, verbose=False
        )
        # Safely extract the final text part
        return response[-1].content.parts[0].text
        return "<h3>Sorry, no plan generated. Try again!</h3>"
    
    async def process_personal_function(query: str):
        global html_list
        # Optional: Add a nice loading bubble
        loading_bubble = ft.Container(
            content=ft.Row([
                ft.ProgressRing(width=20, height=20, stroke_width=3),
                ft.Text("Crafting your perfect trip plan...", color=ft.Colors.GREY_400),
            ], spacing=10),
            bgcolor=ft.Colors.GREEN_900,
            padding=15,
            border_radius=20,
            margin=ft.margin.only(left=80, bottom=20),
        )
        chat_history.controls.append(loading_bubble)
        page.update()

        try:
            new_html = await run_agent(query, runner)  # This is the only correct way

            # Remove loading
            chat_history.controls.remove(loading_bubble)

            # Save and show result
            html_list.append(new_html)
            current_index = len(html_list) - 1

            expand_btn = ft.ElevatedButton(
                f"Expand Plan #{len(html_list)}",
                icon=ft.Icons.AUTO_AWESOME_MOTION_OUTLINED,
                bgcolor=ft.Colors.PURPLE_600,
                color=ft.Colors.WHITE,
                height=60,
                width=300,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=30)),
                on_click=lambda e, idx=current_index: open_full_plan(html_list[idx]),
            )

            chat_history.controls.append(
                ft.Container(
                    ft.Column([
                        ft.Text("Your personalized plan is ready!", weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400),
                        expand_btn,
                    ], spacing=10),
                    bgcolor=ft.Colors.GREEN_900,
                    padding=15,
                    border_radius=20,
                    margin=ft.margin.only(left=80, bottom=20),
                    alignment=ft.alignment.center_left,
                )
            )

        except Exception as e:
            if loading_bubble in chat_history.controls:
                chat_history.controls.remove(loading_bubble)
            chat_history.controls.append(
                ft.Container(ft.Text(f"Error: {e}", color=ft.Colors.RED), bgcolor=ft.Colors.RED_900, padding=15)
            )

        page.update()
        page.scroll_to(delta=10000, duration=500)

    # ====================== FULL PLAN WINDOW ======================
    def open_full_plan(html_content: str):
                
        # Write HTML to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html_content)
            temp_path = f.name
        
        # Open in default browser
        webbrowser.open(f'file://{os.path.abspath(temp_path)}')
        

    # ====================== LAYOUT ======================
    page.add(
        ft.Row([
            ft.Container(expand=False),
            ft.Column([credential_card, main_ui], alignment="center", horizontal_alignment="center", expand=True),
            ft.Container(expand=False),
        ], expand=True, alignment="center")
    )

    page.update()

ft.app(target=main)