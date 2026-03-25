"""FAQ service for common Avni questions.

Pre-built FAQ database that can be served without LLM calls.
Organised by category, searchable, with "Was this helpful?" tracking.

Categories:
- Getting Started (8 FAQs)
- Data Collection (8 FAQs)
- Sync & Connectivity (6 FAQs)
- Forms & Data (6 FAQs)
- Reports (5 FAQs)
- Administration (5 FAQs)
- Troubleshooting (5 FAQs)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class FAQ:
    """A single frequently asked question with answer and metadata."""

    id: str
    question: str
    answer: str  # Markdown formatted
    category: str
    tags: list[str] = field(default_factory=list)
    related_faqs: list[str] = field(default_factory=list)
    helpful_count: int = 0
    not_helpful_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
            "tags": self.tags,
            "related_faqs": self.related_faqs,
            "helpful_count": self.helpful_count,
            "not_helpful_count": self.not_helpful_count,
        }


# Thread-safe counter for helpful/not-helpful tracking
_feedback_lock = Lock()


# ---------------------------------------------------------------------------
# FAQ definitions
# ---------------------------------------------------------------------------

def _build_faqs() -> list[FAQ]:
    """Build the complete FAQ database."""
    faqs: list[FAQ] = []

    # -----------------------------------------------------------------------
    # Getting Started (8 FAQs)
    # -----------------------------------------------------------------------

    faqs.append(FAQ(
        id="gs-001",
        question="How do I install the Avni app on my phone?",
        answer=(
            "The Avni app is available for Android phones.\n\n"
            "**Steps:**\n"
            "1. Open the **Google Play Store** on your phone\n"
            "2. Search for **'Avni'** in the search bar\n"
            "3. Tap **Install** and wait for it to download\n"
            "4. Once installed, tap **Open**\n"
            "5. The app will ask for the server URL -- enter the URL your admin gave you "
            "(usually `https://app.avniproject.org`)\n\n"
            "**Note:** You need Android 6.0 or higher. If you don't find the app, "
            "your phone may be too old."
        ),
        category="Getting Started",
        tags=["install", "download", "play store", "android", "setup"],
        related_faqs=["gs-002", "gs-003"],
    ))

    faqs.append(FAQ(
        id="gs-002",
        question="How do I log in to the Avni app?",
        answer=(
            "You need a username and password from your organisation admin.\n\n"
            "**Steps:**\n"
            "1. Open the Avni app\n"
            "2. Enter your **username** (usually your email or phone number)\n"
            "3. Enter your **password**\n"
            "4. Tap **Login**\n"
            "5. The app will start syncing data -- this may take a few minutes the first time\n\n"
            "**Common issues:**\n"
            "- Make sure there are no extra spaces in your username\n"
            "- Passwords are case-sensitive (capital and small letters matter)\n"
            "- You need internet for the first login"
        ),
        category="Getting Started",
        tags=["login", "sign in", "username", "password", "authentication"],
        related_faqs=["gs-001", "ts-001"],
    ))

    faqs.append(FAQ(
        id="gs-003",
        question="How do I set up my first form?",
        answer=(
            "Forms are set up by your admin in the Avni web portal, not in the phone app.\n\n"
            "**If you are an admin:**\n"
            "1. Log in to `https://app.avniproject.org`\n"
            "2. Go to **App Designer**\n"
            "3. Click **Forms** in the left menu\n"
            "4. Click **+ Create Form**\n"
            "5. Choose the form type (Registration, Encounter, etc.)\n"
            "6. Add questions by clicking **Add Form Element**\n"
            "7. Save the form\n"
            "8. Ask your field staff to sync their app to see the new form\n\n"
            "**If you are a field worker:**\n"
            "Ask your admin to set up the form. Once they do, just sync your app and the form will appear."
        ),
        category="Getting Started",
        tags=["form", "create form", "setup", "app designer", "admin"],
        related_faqs=["fd-001", "fd-002"],
    ))

    faqs.append(FAQ(
        id="gs-004",
        question="What is a catchment area?",
        answer=(
            "A catchment is the geographic area you are responsible for. "
            "It decides which people and data you see in the app.\n\n"
            "**Example:** If you are a health worker covering 3 villages, your catchment "
            "will include those 3 villages. You will only see people registered in those villages.\n\n"
            "**Why it matters:**\n"
            "- You can only register new people in your catchment\n"
            "- You only see data from your catchment\n"
            "- If your catchment is wrong, you might see the wrong people or no people at all\n\n"
            "Your admin assigns catchments. If you think yours is wrong, contact your admin."
        ),
        category="Getting Started",
        tags=["catchment", "area", "location", "village", "geography"],
        related_faqs=["ad-002", "gs-006"],
    ))

    faqs.append(FAQ(
        id="gs-005",
        question="Can I use Avni without internet?",
        answer=(
            "**Yes!** Avni works offline.\n\n"
            "You can do these things without internet:\n"
            "- Register new people\n"
            "- Fill forms during visits\n"
            "- View previously synced data\n"
            "- Schedule visits\n\n"
            "You **need internet** to:\n"
            "- Log in for the first time\n"
            "- Sync your data (upload what you entered and download new data)\n"
            "- View reports on the web\n\n"
            "**Tip:** Sync at least once a day when you have internet (morning or evening) "
            "so your data is backed up on the server."
        ),
        category="Getting Started",
        tags=["offline", "internet", "no network", "wifi", "mobile data"],
        related_faqs=["sc-002", "sc-001"],
    ))

    faqs.append(FAQ(
        id="gs-006",
        question="What are subject types in Avni?",
        answer=(
            "Subject types define the kind of people or entities you register in Avni.\n\n"
            "**Common subject types:**\n"
            "- **Individual** -- a single person (e.g., a pregnant woman, a child, a farmer)\n"
            "- **Household** -- a family or household\n"
            "- **Group** -- a self-help group, village committee, etc.\n\n"
            "Your organisation's admin decides which subject types to use. "
            "When you tap the '+' button in the app to register someone new, "
            "you will see the subject types available to you."
        ),
        category="Getting Started",
        tags=["subject type", "individual", "household", "group", "register"],
        related_faqs=["dc-001", "gs-004"],
    ))

    faqs.append(FAQ(
        id="gs-007",
        question="What are programs in Avni?",
        answer=(
            "Programs let you track a person through a specific journey over time.\n\n"
            "**Examples:**\n"
            "- **Antenatal Care (ANC)** -- tracking a woman from pregnancy to delivery\n"
            "- **Nutrition Program** -- tracking a child's growth over months\n"
            "- **TB Treatment** -- tracking a patient through their treatment course\n\n"
            "A person can be enrolled in multiple programs at the same time.\n\n"
            "**How it works:**\n"
            "1. Register a person first\n"
            "2. Then enrol them in a program\n"
            "3. Conduct scheduled visits within the program\n"
            "4. Exit them from the program when done"
        ),
        category="Getting Started",
        tags=["program", "enrolment", "enrol", "anc", "tracking"],
        related_faqs=["dc-003", "gs-006"],
    ))

    faqs.append(FAQ(
        id="gs-008",
        question="What languages does Avni support?",
        answer=(
            "Avni supports multiple Indian languages.\n\n"
            "**Supported languages include:**\n"
            "Hindi, Marathi, Gujarati, Tamil, Telugu, Kannada, Bengali, Odia, Punjabi, Malayalam, and English.\n\n"
            "**How to change language:**\n"
            "1. Open Avni app\n"
            "2. Go to Settings (3 dots menu > Settings)\n"
            "3. Select your preferred language\n"
            "4. The app will reload in the chosen language\n\n"
            "**Note:** The language of form questions depends on how your admin set up the forms. "
            "If forms are not translated, questions will appear in English even if you change the app language."
        ),
        category="Getting Started",
        tags=["language", "hindi", "marathi", "translation", "locale"],
        related_faqs=["gs-001"],
    ))

    # -----------------------------------------------------------------------
    # Data Collection (8 FAQs)
    # -----------------------------------------------------------------------

    faqs.append(FAQ(
        id="dc-001",
        question="How do I register a new beneficiary?",
        answer=(
            "**Steps:**\n"
            "1. Open the Avni app\n"
            "2. Tap the **+** button (bottom right of home screen)\n"
            "3. Select the type of person to register (e.g., Individual)\n"
            "4. Fill in the registration form\n"
            "5. Tap **Save** at the bottom\n\n"
            "The person is now registered on your phone. "
            "Remember to **sync** to upload their data to the server.\n\n"
            "**Tips:**\n"
            "- Fill in all mandatory fields (marked with *)\n"
            "- Double-check the name and date of birth\n"
            "- You can edit the details later if you make a mistake"
        ),
        category="Data Collection",
        tags=["register", "new person", "beneficiary", "add", "create"],
        related_faqs=["gs-006", "dc-002"],
    ))

    faqs.append(FAQ(
        id="dc-002",
        question="How do I fill a form during a visit?",
        answer=(
            "**Steps:**\n"
            "1. Open the Avni app\n"
            "2. Search for the person you are visiting\n"
            "3. Tap on their name to open their profile\n"
            "4. Tap **New Visit** or **New Encounter**\n"
            "5. Select the type of visit\n"
            "6. Fill in the form\n"
            "7. Tap **Save**\n\n"
            "If you see a scheduled visit in the person's profile, you can tap on it directly.\n\n"
            "**Note:** Some forms appear only if the person meets certain conditions "
            "(e.g., enrolled in a specific program)."
        ),
        category="Data Collection",
        tags=["visit", "encounter", "fill form", "data entry"],
        related_faqs=["dc-001", "dc-003"],
    ))

    faqs.append(FAQ(
        id="dc-003",
        question="How do I enrol someone in a program?",
        answer=(
            "**Steps:**\n"
            "1. First, the person must be registered (see 'How do I register a new beneficiary?')\n"
            "2. Open the person's profile\n"
            "3. Tap **Enrol** or **Enrol in Program**\n"
            "4. Select the program (e.g., ANC, Nutrition)\n"
            "5. Fill in the enrolment form\n"
            "6. Tap **Save**\n\n"
            "After enrolment, scheduled visits for that program will appear on your home screen.\n\n"
            "**Note:** A person can be enrolled in multiple programs at the same time."
        ),
        category="Data Collection",
        tags=["enrol", "program", "enrolment", "anc", "join"],
        related_faqs=["gs-007", "dc-002"],
    ))

    faqs.append(FAQ(
        id="dc-004",
        question="How do I take a photo in a form?",
        answer=(
            "Some forms have a photo field. Here is how to use it:\n\n"
            "1. When you reach the photo field in the form, tap the **camera icon**\n"
            "2. Your phone's camera will open\n"
            "3. Take the photo and tap **OK** or the checkmark\n"
            "4. The photo will be added to the form\n"
            "5. Continue filling the rest of the form and save\n\n"
            "**Tips:**\n"
            "- Make sure the photo is clear and not blurry\n"
            "- Photos are stored on your phone and synced when you have internet\n"
            "- Large photos may make syncing slower\n"
            "- If the camera doesn't open, check that you gave Avni camera permission:\n"
            "  Settings > Apps > Avni > Permissions > Camera = Allowed"
        ),
        category="Data Collection",
        tags=["photo", "camera", "image", "picture", "upload"],
        related_faqs=["dc-002", "dc-005"],
    ))

    faqs.append(FAQ(
        id="dc-005",
        question="Can I edit data after saving a form?",
        answer=(
            "**Yes**, you can edit data you have already saved.\n\n"
            "**Steps:**\n"
            "1. Open the person's profile\n"
            "2. Find the visit or registration you want to edit\n"
            "3. Tap on it\n"
            "4. Tap **Edit** (pencil icon)\n"
            "5. Change the data\n"
            "6. Tap **Save**\n\n"
            "**Important:**\n"
            "- You can only edit data on your phone before it is synced\n"
            "- After sync, editing depends on your organisation's settings\n"
            "- Some organisations allow edits after sync, some don't\n"
            "- Ask your admin if you need to change data that has already been synced"
        ),
        category="Data Collection",
        tags=["edit", "change", "modify", "update", "correct"],
        related_faqs=["dc-002", "dc-006"],
    ))

    faqs.append(FAQ(
        id="dc-006",
        question="What are drafts and how do I use them?",
        answer=(
            "A **draft** is a form that you started filling but did not finish.\n\n"
            "**How drafts work:**\n"
            "- If you start filling a form and press the back button, the app may save it as a draft\n"
            "- Drafts are saved on your phone only (not synced to the server)\n"
            "- You can find drafts on the home screen or in the person's profile\n\n"
            "**To complete a draft:**\n"
            "1. Look for a 'Drafts' section on the home screen, or open the person's profile\n"
            "2. Tap on the draft\n"
            "3. Finish filling the form\n"
            "4. Tap **Save**\n\n"
            "**Tip:** Try to complete forms in one go. Drafts are not synced, "
            "so if you uninstall the app, drafts will be lost."
        ),
        category="Data Collection",
        tags=["draft", "incomplete", "save later", "partial", "unfinished"],
        related_faqs=["dc-005", "dc-002"],
    ))

    faqs.append(FAQ(
        id="dc-007",
        question="How do I schedule a visit for a beneficiary?",
        answer=(
            "Visits in Avni can be scheduled automatically or manually.\n\n"
            "**Automatic scheduling:**\n"
            "Most visits are scheduled automatically by the system based on rules "
            "(e.g., ANC visit every month). Your admin sets these rules.\n\n"
            "**Finding scheduled visits:**\n"
            "1. Open the Avni app\n"
            "2. The home screen shows your pending visits for today\n"
            "3. Tap on a visit to start the form\n\n"
            "**If a visit is missing from your schedule:**\n"
            "- Sync your app first\n"
            "- Check the person's profile -- the scheduled visit should appear there\n"
            "- If it is still missing, the visit scheduling rule may need to be checked by your admin"
        ),
        category="Data Collection",
        tags=["schedule", "visit", "planned", "upcoming", "calendar"],
        related_faqs=["dc-002", "dc-003"],
    ))

    faqs.append(FAQ(
        id="dc-008",
        question="How do I exit someone from a program?",
        answer=(
            "When a person's journey in a program is complete (e.g., after delivery in ANC), "
            "you exit them from the program.\n\n"
            "**Steps:**\n"
            "1. Open the person's profile\n"
            "2. Go to the program section\n"
            "3. Look for an **Exit** option\n"
            "4. Fill in the exit form (if any)\n"
            "5. Tap **Save**\n\n"
            "After exit, no more visits will be scheduled for that program.\n"
            "The person's program data is still preserved for reporting.\n\n"
            "**Note:** Exiting is different from deleting. Exit means the program is complete. "
            "The data is kept for records."
        ),
        category="Data Collection",
        tags=["exit", "program exit", "complete", "discharge", "end"],
        related_faqs=["dc-003", "gs-007"],
    ))

    # -----------------------------------------------------------------------
    # Sync & Connectivity (6 FAQs)
    # -----------------------------------------------------------------------

    faqs.append(FAQ(
        id="sc-001",
        question="How often should I sync?",
        answer=(
            "**Sync at least once a day**, ideally at the end of your workday.\n\n"
            "**Why daily sync matters:**\n"
            "- Your data is backed up on the server (safe if your phone is lost or damaged)\n"
            "- Your supervisor and admin can see your work\n"
            "- Reports get updated\n"
            "- You receive any new data or form changes from admin\n\n"
            "**Best times to sync:**\n"
            "- Morning before going to the field (to get latest data)\n"
            "- Evening after returning from the field (to upload your work)\n\n"
            "**Tip:** If you have WiFi at home or office, sync there. "
            "WiFi is faster and doesn't use your mobile data."
        ),
        category="Sync & Connectivity",
        tags=["sync", "frequency", "how often", "daily", "upload"],
        related_faqs=["sc-002", "sc-003"],
    ))

    faqs.append(FAQ(
        id="sc-002",
        question="What happens to my data when I'm offline?",
        answer=(
            "**Your data is safe.** Everything you enter offline is saved on your phone.\n\n"
            "When you are offline:\n"
            "- All new registrations, forms, and visits are saved locally on your phone\n"
            "- You can continue working normally\n"
            "- Nothing is lost\n\n"
            "When you go back online and sync:\n"
            "- All your offline work gets uploaded to the server\n"
            "- You receive any updates from other team members\n\n"
            "**Important:** Do NOT uninstall the app or clear app data while you have "
            "un-synced records. That will delete your offline work permanently."
        ),
        category="Sync & Connectivity",
        tags=["offline", "data safe", "no internet", "local", "phone storage"],
        related_faqs=["gs-005", "sc-001"],
    ))

    faqs.append(FAQ(
        id="sc-003",
        question="Sync is taking too long. What can I do?",
        answer=(
            "Sync can take time depending on how much data needs to be transferred.\n\n"
            "**Normal sync times:**\n"
            "- Regular daily sync: 1-5 minutes\n"
            "- First sync or reset sync: 5-30 minutes\n"
            "- Very large organisations: up to 60 minutes\n\n"
            "**Speed up your sync:**\n"
            "1. Use WiFi instead of mobile data\n"
            "2. Sync daily (less data to transfer each time)\n"
            "3. Close other apps while syncing\n"
            "4. Keep the Avni app open during sync (don't switch to other apps)\n"
            "5. Make sure your phone has enough storage space (at least 500 MB free)\n\n"
            "If sync regularly takes more than 30 minutes, tell your admin. They may need to "
            "review the data volume in your catchment."
        ),
        category="Sync & Connectivity",
        tags=["slow sync", "long sync", "speed", "performance", "timeout"],
        related_faqs=["sc-001", "ts-002"],
    ))

    faqs.append(FAQ(
        id="sc-004",
        question="Does syncing use a lot of mobile data?",
        answer=(
            "It depends on how much data you have.\n\n"
            "**Approximate data usage:**\n"
            "- Regular daily sync: 1-5 MB\n"
            "- First sync: 10-50 MB (depending on organisation size)\n"
            "- Sync with photos: photos can be 1-5 MB each\n\n"
            "**To reduce data usage:**\n"
            "1. Sync on WiFi when possible\n"
            "2. Sync regularly (small daily syncs use less data than one big weekly sync)\n"
            "3. Compress photos before adding to forms (if your phone has this option)\n\n"
            "If you are worried about data costs, ask your organisation if they can "
            "provide a data reimbursement."
        ),
        category="Sync & Connectivity",
        tags=["data usage", "mobile data", "MB", "cost", "bandwidth"],
        related_faqs=["sc-003", "sc-001"],
    ))

    faqs.append(FAQ(
        id="sc-005",
        question="What does 'Reset Sync' do?",
        answer=(
            "**Reset Sync** deletes all data on your phone and re-downloads everything from the server.\n\n"
            "**When to use it:**\n"
            "- Sync is stuck and won't complete\n"
            "- Your admin made major changes to forms\n"
            "- Your admin asks you to reset sync\n\n"
            "**Steps:**\n"
            "1. First, make sure all your data is synced (check that pending count is 0)\n"
            "2. Go to Settings > Reset Sync\n"
            "3. Confirm\n"
            "4. Wait for the full re-download to complete\n\n"
            "**WARNING:** If you have un-synced data (pending count > 0), that data will "
            "be LOST when you reset. Sync first, then reset."
        ),
        category="Sync & Connectivity",
        tags=["reset sync", "re-download", "fresh sync", "clear data"],
        related_faqs=["sc-003", "ts-002"],
    ))

    faqs.append(FAQ(
        id="sc-006",
        question="Can two people work on the same catchment area?",
        answer=(
            "**Yes**, multiple field workers can be assigned to the same catchment.\n\n"
            "**How it works:**\n"
            "- Each person can register and visit beneficiaries in the shared area\n"
            "- When both sync, they will see each other's data\n"
            "- If two people edit the same record, the last synced version wins\n\n"
            "**Best practices:**\n"
            "- Divide work clearly (e.g., by village or by day)\n"
            "- Sync frequently to stay up to date with each other's entries\n"
            "- Communicate to avoid duplicate registrations\n\n"
            "Your admin sets up catchment assignments in the web portal."
        ),
        category="Sync & Connectivity",
        tags=["shared", "multiple users", "catchment", "team", "collaboration"],
        related_faqs=["gs-004", "ad-001"],
    ))

    # -----------------------------------------------------------------------
    # Forms & Data (6 FAQs)
    # -----------------------------------------------------------------------

    faqs.append(FAQ(
        id="fd-001",
        question="How do I add a new field to a form?",
        answer=(
            "Form fields are added by your admin in the web portal.\n\n"
            "**If you are an admin:**\n"
            "1. Log in to `https://app.avniproject.org`\n"
            "2. Go to **App Designer > Forms**\n"
            "3. Find and open the form you want to edit\n"
            "4. Click **+ Add Form Element** in the desired group\n"
            "5. Set the field name, data type, and options\n"
            "6. Click **Save**\n\n"
            "After saving, all field workers need to **sync** their app to see the new field.\n\n"
            "**If you are a field worker:**\n"
            "You cannot add fields yourself. Ask your admin to add the field and then sync your app."
        ),
        category="Forms & Data",
        tags=["add field", "new question", "form element", "app designer"],
        related_faqs=["fd-002", "gs-003"],
    ))

    faqs.append(FAQ(
        id="fd-002",
        question="How do I make a field mandatory?",
        answer=(
            "Mandatory fields require the user to fill them before saving the form.\n\n"
            "**If you are an admin:**\n"
            "1. Go to **App Designer > Forms**\n"
            "2. Open the form\n"
            "3. Click on the field you want to make mandatory\n"
            "4. Check the **Mandatory** checkbox\n"
            "5. Save the form\n\n"
            "Mandatory fields show a * next to the question. "
            "The form cannot be saved until all mandatory fields are filled.\n\n"
            "**Tip:** Only make fields mandatory if they are truly essential. "
            "Too many mandatory fields can slow down data entry in the field."
        ),
        category="Forms & Data",
        tags=["mandatory", "required", "compulsory", "must fill", "validation"],
        related_faqs=["fd-001", "fd-003"],
    ))

    faqs.append(FAQ(
        id="fd-003",
        question="What are skip logic rules?",
        answer=(
            "Skip logic (also called display rules) controls which questions appear based on "
            "previous answers.\n\n"
            "**Example:**\n"
            "- Question: 'Is the woman pregnant?' (Yes/No)\n"
            "- If **Yes**: show 'Number of weeks pregnant'\n"
            "- If **No**: skip that question\n\n"
            "**Why it matters:**\n"
            "- Makes forms shorter and faster to fill\n"
            "- Shows only relevant questions\n"
            "- Reduces errors\n\n"
            "**If questions seem missing from a form**, it might be because of skip logic. "
            "Check your answers to previous questions.\n\n"
            "Skip logic is set up by your admin in the **App Designer** using form rules."
        ),
        category="Forms & Data",
        tags=["skip logic", "display rule", "conditional", "show hide", "form rule"],
        related_faqs=["fd-002", "fd-004"],
    ))

    faqs.append(FAQ(
        id="fd-004",
        question="What data types can form fields have?",
        answer=(
            "Avni supports many data types for form fields:\n\n"
            "| Type | Use For | Example |\n"
            "|------|---------|----------|\n"
            "| **Text** | Names, descriptions | 'Ramesh Kumar' |\n"
            "| **Numeric** | Numbers, measurements | Age: 25, Weight: 65 |\n"
            "| **Date** | Dates | Date of birth: 15/03/1998 |\n"
            "| **Coded (Single)** | Pick one option | Gender: Male/Female |\n"
            "| **Coded (Multi)** | Pick multiple options | Symptoms: Fever, Cough, Headache |\n"
            "| **Image** | Photos | Photo of health card |\n"
            "| **Location** | GPS coordinates | Visit location |\n"
            "| **Notes** | Long text | Observations |\n\n"
            "Your admin chooses the right data type when creating each field."
        ),
        category="Forms & Data",
        tags=["data type", "text", "numeric", "coded", "date", "field type"],
        related_faqs=["fd-001", "fd-003"],
    ))

    faqs.append(FAQ(
        id="fd-005",
        question="How do I delete a record?",
        answer=(
            "In most cases, you **cannot delete** records from the phone app. "
            "This is by design to prevent accidental data loss.\n\n"
            "**If you registered the wrong person or made a major error:**\n"
            "1. Contact your organisation admin\n"
            "2. They can void or mark the record as inactive from the web portal\n"
            "3. After they make the change, sync your app\n\n"
            "**If you want to correct data (not delete):**\n"
            "1. Open the person's profile\n"
            "2. Tap Edit\n"
            "3. Change the incorrect data\n"
            "4. Save\n\n"
            "**Why no delete?** In health and social programs, maintaining a complete record "
            "is important for auditing and reporting."
        ),
        category="Forms & Data",
        tags=["delete", "remove", "void", "undo", "mistake"],
        related_faqs=["dc-005", "fd-001"],
    ))

    faqs.append(FAQ(
        id="fd-006",
        question="How do I add dropdown options to a field?",
        answer=(
            "Dropdown options are configured using **Concepts** in Avni.\n\n"
            "**If you are an admin:**\n"
            "1. Go to **App Designer > Concepts**\n"
            "2. Create a new Coded concept (or edit an existing one)\n"
            "3. Add the answer options (e.g., for 'Blood Group': A+, A-, B+, B-, AB+, AB-, O+, O-)\n"
            "4. Save the concept\n"
            "5. Go to the form and add a field using this concept\n"
            "6. Set the type to Single Select or Multi Select\n"
            "7. Save the form\n\n"
            "After saving, field workers need to sync to see the updated options."
        ),
        category="Forms & Data",
        tags=["dropdown", "options", "coded", "concept", "select", "choices"],
        related_faqs=["fd-001", "fd-004"],
    ))

    # -----------------------------------------------------------------------
    # Reports (5 FAQs)
    # -----------------------------------------------------------------------

    faqs.append(FAQ(
        id="rp-001",
        question="How do I view reports?",
        answer=(
            "Reports are available in two places:\n\n"
            "**On the web portal (recommended for detailed reports):**\n"
            "1. Log in to `https://app.avniproject.org`\n"
            "2. Click **Reports** in the top menu\n"
            "3. Choose the report you want to view\n"
            "4. Set filters (date range, location, etc.)\n"
            "5. Click **View** or **Generate**\n\n"
            "**In the phone app (basic reports):**\n"
            "1. Open Avni\n"
            "2. Look for a Reports tab (if available for your organisation)\n\n"
            "**Note:** You need the right permissions to view reports. "
            "If you don't see any reports, ask your admin."
        ),
        category="Reports",
        tags=["report", "view", "dashboard", "analytics", "statistics"],
        related_faqs=["rp-002", "rp-003"],
    ))

    faqs.append(FAQ(
        id="rp-002",
        question="How do I export data to Excel?",
        answer=(
            "Data can be exported from the Avni web portal.\n\n"
            "**Steps:**\n"
            "1. Log in to `https://app.avniproject.org`\n"
            "2. Go to **Reports** section\n"
            "3. Look for an **Export** option\n"
            "4. Select what to export:\n"
            "   - Subject type (e.g., Individual)\n"
            "   - Program (e.g., ANC)\n"
            "   - Encounter type (e.g., Monthly Visit)\n"
            "5. Set your filters (date range, location)\n"
            "6. Click **Export** or **Download**\n"
            "7. Save the Excel/CSV file\n\n"
            "**Note:** You need admin or data export privileges. "
            "If you don't see the export option, ask your admin."
        ),
        category="Reports",
        tags=["export", "excel", "csv", "download", "data"],
        related_faqs=["rp-001", "rp-003"],
    ))

    faqs.append(FAQ(
        id="rp-003",
        question="Why are my report numbers different from what I expect?",
        answer=(
            "Report discrepancies usually have a simple explanation:\n\n"
            "**Common reasons:**\n"
            "1. **Un-synced data** -- If you or your colleagues haven't synced, "
            "recent entries won't appear in reports. Sync all devices first.\n"
            "2. **Date range** -- Check the report's date filter. "
            "You might be looking at a different time period.\n"
            "3. **Location filter** -- Reports may be filtered to a specific area. "
            "Check if a location filter is active.\n"
            "4. **Report calculation** -- Some reports count unique persons, "
            "others count visits. Make sure you understand what the number represents.\n"
            "5. **Delayed update** -- Some reports refresh once a day, not in real-time.\n\n"
            "If numbers are still wrong after checking these, contact your admin with specifics."
        ),
        category="Reports",
        tags=["wrong numbers", "mismatch", "discrepancy", "count", "incorrect"],
        related_faqs=["rp-001", "sc-001"],
    ))

    faqs.append(FAQ(
        id="rp-004",
        question="Can I create custom reports?",
        answer=(
            "Custom reports are set up by your admin or the Avni implementation team.\n\n"
            "**Options for custom reporting:**\n"
            "1. **Built-in report cards** -- Your admin can configure report cards in App Designer\n"
            "2. **Metabase dashboards** -- Avni integrates with Metabase for advanced analytics\n"
            "3. **Data export + Excel** -- Export data and build your own Excel reports\n\n"
            "**If you need a specific report:**\n"
            "Write down exactly what you want to see (e.g., 'Number of pregnant women by village, "
            "by month') and share with your admin. They can create or request it."
        ),
        category="Reports",
        tags=["custom report", "create report", "metabase", "dashboard", "analytics"],
        related_faqs=["rp-001", "rp-002"],
    ))

    faqs.append(FAQ(
        id="rp-005",
        question="How do I print a report?",
        answer=(
            "Avni reports can be printed from the web portal.\n\n"
            "**Steps:**\n"
            "1. Open the report on the web portal\n"
            "2. Set your filters and view the report\n"
            "3. Press **Ctrl+P** (or **Cmd+P** on Mac) to open the print dialog\n"
            "4. Select your printer or choose 'Save as PDF'\n"
            "5. Click **Print**\n\n"
            "**From phone (no printer available):**\n"
            "- Take a screenshot of the report (Power + Volume Down)\n"
            "- Share the screenshot via WhatsApp or email\n\n"
            "For regularly needed paper reports, ask your admin about scheduled report generation."
        ),
        category="Reports",
        tags=["print", "pdf", "paper", "screenshot", "share"],
        related_faqs=["rp-001", "rp-002"],
    ))

    # -----------------------------------------------------------------------
    # Administration (5 FAQs)
    # -----------------------------------------------------------------------

    faqs.append(FAQ(
        id="ad-001",
        question="How do I add a new user?",
        answer=(
            "User management is done in the Avni web portal by an admin.\n\n"
            "**Steps:**\n"
            "1. Log in to `https://app.avniproject.org` as admin\n"
            "2. Go to **Admin > Users**\n"
            "3. Click **+ Add User**\n"
            "4. Fill in:\n"
            "   - Username (email or phone number)\n"
            "   - Name\n"
            "   - Role (Field Worker, Admin, etc.)\n"
            "   - Catchment area\n"
            "5. Set a temporary password\n"
            "6. Click **Save**\n"
            "7. Share the username and temporary password with the new user\n\n"
            "The new user can now log in on their phone with these credentials."
        ),
        category="Administration",
        tags=["add user", "new user", "create user", "field worker", "account"],
        related_faqs=["ad-002", "ad-003"],
    ))

    faqs.append(FAQ(
        id="ad-002",
        question="How do I create a new catchment area?",
        answer=(
            "Catchments are created in the Avni web portal.\n\n"
            "**Steps:**\n"
            "1. Log in as admin\n"
            "2. Go to **Admin > Locations**\n"
            "3. Make sure the locations (states, districts, villages, etc.) exist\n"
            "4. Go to **Admin > Catchments**\n"
            "5. Click **+ Create Catchment**\n"
            "6. Give it a name\n"
            "7. Select which locations it includes\n"
            "8. Click **Save**\n\n"
            "After creating a catchment, you can assign users to it. "
            "The assigned users will see data from those locations."
        ),
        category="Administration",
        tags=["catchment", "create catchment", "area", "location", "geography"],
        related_faqs=["gs-004", "ad-001"],
    ))

    faqs.append(FAQ(
        id="ad-003",
        question="How do I reset a user's password?",
        answer=(
            "**Steps:**\n"
            "1. Log in to `https://app.avniproject.org` as admin\n"
            "2. Go to **Admin > Users**\n"
            "3. Find the user whose password needs resetting\n"
            "4. Click on their name\n"
            "5. Click **Reset Password**\n"
            "6. Enter a new temporary password\n"
            "7. Save\n"
            "8. Share the new password with the user securely (in person or phone call, not WhatsApp)\n\n"
            "The user should log in with the new password and change it to something they can remember."
        ),
        category="Administration",
        tags=["password", "reset", "forgot password", "change password"],
        related_faqs=["ad-001", "ts-001"],
    ))

    faqs.append(FAQ(
        id="ad-004",
        question="How do I check which users have synced recently?",
        answer=(
            "Admins can monitor sync activity from the web portal.\n\n"
            "**Steps:**\n"
            "1. Log in as admin\n"
            "2. Go to **Admin > Users**\n"
            "3. Look for the 'Last Synced' column\n"
            "4. Users who haven't synced in over a day may need a reminder\n\n"
            "**Why this is important:**\n"
            "- Un-synced users mean incomplete data and inaccurate reports\n"
            "- Regular monitoring helps catch issues early (phone problems, login issues)\n"
            "- You can contact users who haven't synced to help them resolve any issues\n\n"
            "**Tip:** Set a routine to check sync status weekly."
        ),
        category="Administration",
        tags=["sync status", "monitoring", "last synced", "user activity", "admin"],
        related_faqs=["sc-001", "ad-001"],
    ))

    faqs.append(FAQ(
        id="ad-005",
        question="How do I manage user roles and permissions?",
        answer=(
            "Avni has different roles with different permissions.\n\n"
            "**Common roles:**\n"
            "- **Field Worker** -- Can register people, fill forms, sync data\n"
            "- **Admin** -- Can do everything: manage users, forms, reports, etc.\n"
            "- **Organisation Admin** -- Full control over the organisation\n\n"
            "**To change a user's role:**\n"
            "1. Log in as admin\n"
            "2. Go to Admin > Users\n"
            "3. Click on the user\n"
            "4. Change their role\n"
            "5. Save\n\n"
            "**Note:** Be careful with admin access. Give admin roles only to people who need to "
            "manage forms, users, or reports. Field workers only need the basic role."
        ),
        category="Administration",
        tags=["role", "permission", "access", "admin", "field worker"],
        related_faqs=["ad-001", "ad-003"],
    ))

    # -----------------------------------------------------------------------
    # Troubleshooting (5 FAQs)
    # -----------------------------------------------------------------------

    faqs.append(FAQ(
        id="ts-001",
        question="I can't log in. What should I do?",
        answer=(
            "**Quick fix checklist:**\n\n"
            "1. **Check your username** -- no extra spaces, correct email/phone\n"
            "2. **Check your password** -- passwords are case-sensitive. "
            "Tap the eye icon to see what you typed.\n"
            "3. **Check internet** -- you need internet to log in. "
            "Try opening google.com in your browser.\n"
            "4. **Check server URL** -- Settings > Server URL should be "
            "`https://app.avniproject.org`\n"
            "5. **Try again** -- sometimes the server is briefly unavailable. Wait 5 minutes.\n\n"
            "**If none of this works:**\n"
            "Contact your admin and ask them to:\n"
            "- Check if your account is active\n"
            "- Reset your password"
        ),
        category="Troubleshooting",
        tags=["login", "can't login", "password", "authentication", "access"],
        related_faqs=["gs-002", "ad-003"],
    ))

    faqs.append(FAQ(
        id="ts-002",
        question="Sync keeps failing. What should I do?",
        answer=(
            "**Step-by-step fix:**\n\n"
            "1. **Check internet** -- open google.com in your browser\n"
            "2. **Switch to WiFi** -- if using mobile data, try WiFi instead\n"
            "3. **Close other apps** -- free up phone memory\n"
            "4. **Force close Avni** -- Settings > Apps > Avni > Force Stop, then reopen\n"
            "5. **Clear cache** -- Settings > Apps > Avni > Storage > Clear Cache "
            "(NOT Clear Data!)\n"
            "6. **Try syncing again**\n\n"
            "**If it still fails:**\n"
            "7. Check if you see an error message and tell your admin\n"
            "8. As a last resort, try **Settings > Reset Sync** "
            "(only if all your data is already synced)\n\n"
            "**Important:** Never uninstall the app if you have un-synced data."
        ),
        category="Troubleshooting",
        tags=["sync fail", "sync error", "not syncing", "sync problem"],
        related_faqs=["sc-001", "sc-005"],
    ))

    faqs.append(FAQ(
        id="ts-003",
        question="The app is very slow. How can I speed it up?",
        answer=(
            "**Quick fixes:**\n\n"
            "1. **Restart your phone** -- this clears temporary memory\n"
            "2. **Close other apps** -- too many apps running makes everything slow\n"
            "3. **Free up storage** -- delete old photos, videos, or unused apps. "
            "You need at least 500 MB free.\n"
            "4. **Update the app** -- newer versions are often faster. "
            "Check Play Store for updates.\n"
            "5. **Sync regularly** -- daily sync keeps data manageable\n\n"
            "**If still slow:**\n"
            "- Your phone may not have enough RAM (Avni works best with 2 GB+ RAM)\n"
            "- Your catchment may have too many records -- ask admin to check\n"
            "- Report the issue to your admin with your phone model name"
        ),
        category="Troubleshooting",
        tags=["slow", "performance", "speed", "lag", "hang", "freeze"],
        related_faqs=["ts-002", "sc-003"],
    ))

    faqs.append(FAQ(
        id="ts-004",
        question="I accidentally registered the wrong person. What do I do?",
        answer=(
            "**Don't panic.** Here is what to do:\n\n"
            "**If you haven't synced yet:**\n"
            "The incorrect record is only on your phone. "
            "Unfortunately, you can't delete it from the app, but once you sync, "
            "your admin can void it from the web portal.\n\n"
            "**Steps:**\n"
            "1. Sync your app so the record goes to the server\n"
            "2. Contact your admin with:\n"
            "   - The person's name (the incorrect one)\n"
            "   - When you registered them\n"
            "3. Ask the admin to void the record\n"
            "4. Register the correct person\n"
            "5. Sync again\n\n"
            "**Tip:** To avoid this, double-check details before tapping Save."
        ),
        category="Troubleshooting",
        tags=["wrong person", "mistake", "error", "incorrect", "undo", "void"],
        related_faqs=["dc-001", "fd-005"],
    ))

    faqs.append(FAQ(
        id="ts-005",
        question="My phone was lost or stolen. Is my data safe?",
        answer=(
            "**If you synced regularly, your data is safe on the server.**\n\n"
            "**Immediate steps:**\n"
            "1. **Tell your admin immediately** -- they should disable your account so "
            "no one else can access it\n"
            "2. **Check what was synced** -- your admin can tell you the last sync date "
            "and what data is on the server\n\n"
            "**Getting back to work:**\n"
            "1. Get a new phone\n"
            "2. Install Avni from the Play Store\n"
            "3. Ask your admin to:\n"
            "   - Reset your password\n"
            "   - Re-enable your account\n"
            "4. Log in and sync -- all your synced data will download\n\n"
            "**Data you entered but didn't sync is lost.** This is why daily sync is so important.\n\n"
            "**Security:** Avni data on the phone is not encrypted with a separate PIN. "
            "The phone's own lock screen is the first line of defence."
        ),
        category="Troubleshooting",
        tags=["lost phone", "stolen", "data loss", "security", "new phone"],
        related_faqs=["sc-001", "sc-002"],
    ))

    return faqs


# ---------------------------------------------------------------------------
# FAQ registry
# ---------------------------------------------------------------------------

_FAQ_DB: dict[str, FAQ] = {}
_FAQ_BY_CATEGORY: dict[str, list[FAQ]] = {}


def _init_faqs() -> None:
    """Build the FAQ database. Called once on first access."""
    if _FAQ_DB:
        return

    for faq in _build_faqs():
        _FAQ_DB[faq.id] = faq
        _FAQ_BY_CATEGORY.setdefault(faq.category, []).append(faq)

    logger.info("Initialised %d FAQs across %d categories", len(_FAQ_DB), len(_FAQ_BY_CATEGORY))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_all_faqs() -> list[FAQ]:
    """Return all FAQs."""
    _init_faqs()
    return list(_FAQ_DB.values())


def get_faqs_by_category(category: str) -> list[FAQ]:
    """Return FAQs for a specific category.

    Returns an empty list if the category does not exist.
    """
    _init_faqs()
    return _FAQ_BY_CATEGORY.get(category, [])


def get_categories() -> list[str]:
    """Return all FAQ category names."""
    _init_faqs()
    return sorted(_FAQ_BY_CATEGORY.keys())


def get_faq(faq_id: str) -> FAQ | None:
    """Return a specific FAQ by ID, or None if not found."""
    _init_faqs()
    return _FAQ_DB.get(faq_id)


def search_faqs(query: str) -> list[FAQ]:
    """Search FAQs by keyword matching on question, answer, and tags.

    Returns results sorted by relevance (keyword match count).
    """
    _init_faqs()

    if not query or not query.strip():
        return list(_FAQ_DB.values())

    keywords = query.lower().split()
    scored: list[tuple[int, FAQ]] = []

    for faq in _FAQ_DB.values():
        score = 0
        searchable = f"{faq.question} {faq.answer} {' '.join(faq.tags)} {faq.category}".lower()

        for kw in keywords:
            if kw in searchable:
                # Weight question matches higher than answer matches
                if kw in faq.question.lower():
                    score += 3
                if kw in " ".join(faq.tags).lower():
                    score += 2
                if kw in faq.answer.lower():
                    score += 1

        if score > 0:
            scored.append((score, faq))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [faq for _, faq in scored]


def mark_helpful(faq_id: str, helpful: bool) -> bool:
    """Record whether a user found an FAQ helpful.

    Returns True if the FAQ was found and updated, False otherwise.
    """
    _init_faqs()

    faq = _FAQ_DB.get(faq_id)
    if faq is None:
        return False

    with _feedback_lock:
        if helpful:
            faq.helpful_count += 1
        else:
            faq.not_helpful_count += 1

    logger.info(
        "FAQ %s marked as %s (helpful=%d, not_helpful=%d)",
        faq_id,
        "helpful" if helpful else "not helpful",
        faq.helpful_count,
        faq.not_helpful_count,
    )
    return True
