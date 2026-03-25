"""Guided troubleshooting for common Avni issues.

Pre-built decision trees that walk non-technical users through
diagnosing and fixing common problems step-by-step.

Categories:
1. Sync Issues (most common -- 40% of support tickets)
2. Login/Authentication Problems
3. Form Not Showing
4. App Crashes/Performance
5. Can't Find My Data
6. Report Is Wrong
7. How to Export Data
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TroubleshootOption:
    """A single choice the user can make at a troubleshooting step."""

    label: str
    next_step_id: str | None = None  # None means this is a terminal step
    solution: str | None = None  # Displayed when terminal

    def to_dict(self) -> dict:
        result: dict = {"label": self.label}
        if self.next_step_id is not None:
            result["next_step_id"] = self.next_step_id
        if self.solution is not None:
            result["solution"] = self.solution
        return result


@dataclass
class TroubleshootStep:
    """A single step in a troubleshooting decision tree."""

    id: str
    question: str
    help_text: str
    options: list[TroubleshootOption] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "help_text": self.help_text,
            "options": [o.to_dict() for o in self.options],
        }


@dataclass
class TroubleshootFlow:
    """A complete troubleshooting decision tree for one issue category."""

    id: str
    title: str
    description: str
    category: str
    steps: dict[str, TroubleshootStep] = field(default_factory=dict)
    start_step: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "start_step": self.start_step,
            "steps": {k: v.to_dict() for k, v in self.steps.items()},
        }

    def to_summary(self) -> dict:
        """Return a lightweight summary (no steps) for listing."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "total_steps": len(self.steps),
        }


# ---------------------------------------------------------------------------
# Flow builders
# ---------------------------------------------------------------------------

def _build_sync_flow() -> TroubleshootFlow:
    """Flow 1: Sync is not working."""
    steps: dict[str, TroubleshootStep] = {}

    steps["start"] = TroubleshootStep(
        id="start",
        question="When did sync last work on your device?",
        help_text="Open the Avni app and look at the bottom of the home screen. It shows the last sync time.",
        options=[
            TroubleshootOption(label="It has never synced successfully", next_step_id="never_synced"),
            TroubleshootOption(label="It worked before but stopped recently", next_step_id="stopped_recently"),
            TroubleshootOption(label="Syncing is very slow", next_step_id="slow_sync"),
        ],
    )

    # --- Never synced branch ---
    steps["never_synced"] = TroubleshootStep(
        id="never_synced",
        question="Is your phone connected to the internet right now?",
        help_text="Check if you can open a website (like google.com) in your phone browser. If it opens, you have internet.",
        options=[
            TroubleshootOption(
                label="No, I don't have internet",
                solution=(
                    "You need an internet connection to sync. "
                    "Turn on WiFi or mobile data:\n\n"
                    "1. Swipe down from the top of your screen\n"
                    "2. Tap the WiFi icon to connect to WiFi, OR\n"
                    "3. Tap the Mobile Data icon to use your phone's data\n"
                    "4. Wait 10 seconds, then open Avni and try syncing again"
                ),
            ),
            TroubleshootOption(label="Yes, I have internet", next_step_id="check_server_url"),
        ],
    )

    steps["check_server_url"] = TroubleshootStep(
        id="check_server_url",
        question="Is the server URL correct in your Avni app?",
        help_text=(
            "To check: Open Avni app > tap the 3 dots menu (top right) > Settings. "
            "The server URL should be: https://app.avniproject.org"
        ),
        options=[
            TroubleshootOption(
                label="The URL looks correct",
                solution=(
                    "Your app is set up correctly but sync still fails. This usually means "
                    "your user account is not assigned to a catchment area yet.\n\n"
                    "Please contact your organisation admin and ask them to:\n"
                    "1. Log in to the Avni admin panel (https://app.avniproject.org)\n"
                    "2. Go to Users section\n"
                    "3. Find your username and check that a Catchment is assigned\n"
                    "4. Save and ask you to try syncing again"
                ),
            ),
            TroubleshootOption(
                label="The URL is wrong or empty",
                solution=(
                    "Update the server URL:\n\n"
                    "1. Open Avni app\n"
                    "2. Tap the 3 dots menu (top right)\n"
                    "3. Tap Settings\n"
                    "4. In the Server URL field, type exactly:\n"
                    "   https://app.avniproject.org\n"
                    "5. Tap Save\n"
                    "6. Go back and try syncing again\n\n"
                    "If your organisation uses a different server, ask your admin for the correct URL."
                ),
            ),
        ],
    )

    # --- Stopped recently branch ---
    steps["stopped_recently"] = TroubleshootStep(
        id="stopped_recently",
        question="Do you see any error message when sync fails?",
        help_text="When sync fails, the app usually shows a message at the bottom of the screen. What does it say?",
        options=[
            TroubleshootOption(label="It says 'Sync failed'", next_step_id="sync_failed_error"),
            TroubleshootOption(label="It says 'Unauthorized' or 'Session expired'", next_step_id="unauthorized_error"),
            TroubleshootOption(label="Some other error or no error message", next_step_id="check_pending_count"),
        ],
    )

    steps["sync_failed_error"] = TroubleshootStep(
        id="sync_failed_error",
        question="Are you connected to the internet?",
        help_text="Try opening google.com in your phone browser to check.",
        options=[
            TroubleshootOption(
                label="No, I don't have internet",
                solution=(
                    "Sync needs internet. Connect to WiFi or turn on mobile data, "
                    "then open Avni and try syncing again.\n\n"
                    "Your data is safe -- everything you entered is saved on your phone "
                    "and will sync when you get internet."
                ),
            ),
            TroubleshootOption(
                label="Yes, I have internet",
                solution=(
                    "Try resetting sync:\n\n"
                    "1. Open Avni app\n"
                    "2. Tap the 3 dots menu (top right)\n"
                    "3. Tap Settings\n"
                    "4. Scroll down and tap 'Reset Sync'\n"
                    "5. Tap 'Yes' to confirm\n"
                    "6. Wait for sync to complete (this may take a few minutes)\n\n"
                    "WARNING: Reset Sync will re-download all data. Make sure you are "
                    "on a good WiFi connection and your phone is charged."
                ),
            ),
        ],
    )

    steps["unauthorized_error"] = TroubleshootStep(
        id="unauthorized_error",
        question="",
        help_text="Your login session has expired. This is normal and happens after some time.",
        options=[
            TroubleshootOption(
                label="How do I fix this?",
                solution=(
                    "Log out and log back in:\n\n"
                    "1. Open Avni app\n"
                    "2. Tap the 3 dots menu (top right)\n"
                    "3. Tap 'Logout'\n"
                    "4. Enter your username and password\n"
                    "5. Tap 'Login'\n"
                    "6. Sync will start automatically\n\n"
                    "If you forgot your password, contact your organisation admin to reset it."
                ),
            ),
        ],
    )

    steps["check_pending_count"] = TroubleshootStep(
        id="check_pending_count",
        question="How many pending records do you see on the sync screen?",
        help_text=(
            "Open Avni > tap the sync icon (circular arrows). "
            "It shows how many records are waiting to be uploaded."
        ),
        options=[
            TroubleshootOption(
                label="More than 100 pending records",
                solution=(
                    "You have a lot of data waiting to sync. This needs a strong internet connection:\n\n"
                    "1. Connect to a strong WiFi network (not mobile data)\n"
                    "2. Plug in your phone charger\n"
                    "3. Open Avni and tap Sync\n"
                    "4. Keep the app open and wait -- do not switch to other apps\n"
                    "5. This may take 10-30 minutes depending on the data\n\n"
                    "If sync keeps failing with many records, contact your admin. "
                    "They may need to check the server."
                ),
            ),
            TroubleshootOption(
                label="Less than 100 or I can't see the count",
                solution=(
                    "Try these steps in order:\n\n"
                    "1. Force close the Avni app:\n"
                    "   - On Android: Go to Settings > Apps > Avni > Force Stop\n"
                    "   - On iPhone: Swipe up from bottom, find Avni, swipe it away\n"
                    "2. Clear the app cache:\n"
                    "   - On Android: Settings > Apps > Avni > Storage > Clear Cache\n"
                    "   - (Do NOT tap 'Clear Data' -- that will delete your local records)\n"
                    "3. Reopen the Avni app\n"
                    "4. Try syncing again\n\n"
                    "If it still does not work, contact your organisation admin."
                ),
            ),
        ],
    )

    # --- Slow sync branch ---
    steps["slow_sync"] = TroubleshootStep(
        id="slow_sync",
        question="How long does sync usually take?",
        help_text="Sync time depends on the number of records. A fresh sync can take 5-15 minutes.",
        options=[
            TroubleshootOption(
                label="More than 30 minutes",
                solution=(
                    "Long sync times usually happen when there is a lot of data. Try this:\n\n"
                    "1. Sync on WiFi only (not mobile data)\n"
                    "2. Sync at a time when the internet is not busy (early morning or late evening)\n"
                    "3. Keep the app open while syncing -- don't switch to other apps\n"
                    "4. Make sure your phone has enough storage space:\n"
                    "   Settings > Storage > check you have at least 500 MB free\n\n"
                    "If sync regularly takes more than 30 minutes, tell your admin. "
                    "They may need to review how much data is in your catchment."
                ),
            ),
            TroubleshootOption(
                label="5 to 30 minutes",
                solution=(
                    "This is usually normal, especially if you have many registered beneficiaries.\n\n"
                    "Tips to keep sync fast:\n"
                    "- Sync at least once a day\n"
                    "- Use WiFi when possible\n"
                    "- Keep your phone charged during sync\n"
                    "- Close other apps while syncing"
                ),
            ),
        ],
    )

    return TroubleshootFlow(
        id="sync_not_working",
        title="Sync is not working",
        description="Fix issues with data not syncing between your phone and the server.",
        category="Sync & Connectivity",
        steps=steps,
        start_step="start",
    )


def _build_form_not_showing_flow() -> TroubleshootFlow:
    """Flow 2: Form is not showing."""
    steps: dict[str, TroubleshootStep] = {}

    steps["start"] = TroubleshootStep(
        id="start",
        question="Where are you trying to find the form?",
        help_text="Forms in Avni appear in different places depending on the type of form.",
        options=[
            TroubleshootOption(label="Registration form (to register a new person)", next_step_id="reg_form"),
            TroubleshootOption(label="Visit/encounter form (to fill during a visit)", next_step_id="visit_form"),
            TroubleshootOption(label="Enrolment form (to enrol someone in a program)", next_step_id="enrol_form"),
        ],
    )

    steps["reg_form"] = TroubleshootStep(
        id="reg_form",
        question="When you tap the '+' button on the home screen, do you see the subject type (e.g., Individual, Household)?",
        help_text="The '+' button is usually at the bottom right of the home screen.",
        options=[
            TroubleshootOption(
                label="I don't see the '+' button at all",
                solution=(
                    "You may not have permission to register new people.\n\n"
                    "Contact your organisation admin and ask them to check:\n"
                    "1. Your user role has registration privileges\n"
                    "2. You are assigned to a catchment area\n"
                    "3. The subject type is configured for your organisation"
                ),
            ),
            TroubleshootOption(
                label="I see the '+' but the subject type is missing",
                solution=(
                    "The subject type may not be set up for your organisation.\n\n"
                    "Ask your admin to check in the Avni admin panel:\n"
                    "1. Go to App Designer > Subject Types\n"
                    "2. Make sure the subject type you need exists\n"
                    "3. Go to App Designer > Forms\n"
                    "4. Check that a registration form is linked to that subject type"
                ),
            ),
            TroubleshootOption(label="I see the subject type but the form is blank or has errors", next_step_id="form_blank"),
        ],
    )

    steps["visit_form"] = TroubleshootStep(
        id="visit_form",
        question="When you open a person's profile, do you see the option to start a new visit?",
        help_text="Open a registered person > look for a 'New Visit' or 'New Encounter' button.",
        options=[
            TroubleshootOption(
                label="I don't see any visit option",
                solution=(
                    "The encounter type may not be configured. Ask your admin to check:\n\n"
                    "1. Go to App Designer > Encounter Types\n"
                    "2. Make sure the encounter type exists\n"
                    "3. Check that it is linked to the correct subject type\n"
                    "4. Check that a form is created for this encounter type\n"
                    "5. If it is a program encounter, make sure the person is enrolled in the program first"
                ),
            ),
            TroubleshootOption(
                label="I see the visit option but the form does not load",
                next_step_id="form_blank",
            ),
            TroubleshootOption(
                label="The visit is greyed out or I get an error",
                solution=(
                    "This can happen if:\n\n"
                    "1. A scheduled visit already exists -- check the 'Planned Visits' section\n"
                    "2. A visit rule is preventing it -- some forms only appear on certain dates or conditions\n"
                    "3. You need to sync first -- try syncing, then check again\n\n"
                    "If none of these help, contact your admin with the exact error message."
                ),
            ),
        ],
    )

    steps["enrol_form"] = TroubleshootStep(
        id="enrol_form",
        question="When you open a person's profile, do you see an 'Enrol' option?",
        help_text="The enrol button usually appears on the person's dashboard.",
        options=[
            TroubleshootOption(
                label="I don't see any enrol option",
                solution=(
                    "Programs may not be configured for this subject type.\n\n"
                    "Ask your admin to check:\n"
                    "1. Go to App Designer > Programs\n"
                    "2. Make sure the program exists and is linked to the correct subject type\n"
                    "3. Check that an enrolment form is created for this program\n"
                    "4. Your user role should have enrolment privileges"
                ),
            ),
            TroubleshootOption(
                label="I see the enrol option but the form is blank",
                next_step_id="form_blank",
            ),
        ],
    )

    steps["form_blank"] = TroubleshootStep(
        id="form_blank",
        question="Is the form completely blank, or does it show but with missing fields?",
        help_text="Sometimes a form loads but some questions are missing because of display rules.",
        options=[
            TroubleshootOption(
                label="Completely blank -- no questions at all",
                solution=(
                    "The form definition may be empty or broken. Try:\n\n"
                    "1. Sync your app (tap the sync icon)\n"
                    "2. Wait for sync to finish completely\n"
                    "3. Try opening the form again\n\n"
                    "If still blank, ask your admin to check the form in App Designer -- "
                    "it may have no form elements (questions) added yet."
                ),
            ),
            TroubleshootOption(
                label="Some questions are missing",
                solution=(
                    "Missing questions usually happen because of display rules (skip logic).\n\n"
                    "Some questions only appear when you give a specific answer to a previous question. "
                    "For example, 'Number of weeks pregnant' only shows if you answer 'Yes' to 'Is pregnant?'\n\n"
                    "If you believe a question should be visible but is not:\n"
                    "1. Check your answers to previous questions\n"
                    "2. Sync the app and try again\n"
                    "3. Ask your admin to check the form's skip logic rules"
                ),
            ),
        ],
    )

    return TroubleshootFlow(
        id="form_not_showing",
        title="Form is not showing",
        description="Fix issues where you cannot find or open a form.",
        category="Forms & Data",
        steps=steps,
        start_step="start",
    )


def _build_login_problems_flow() -> TroubleshootFlow:
    """Flow 3: Login problems."""
    steps: dict[str, TroubleshootStep] = {}

    steps["start"] = TroubleshootStep(
        id="start",
        question="What happens when you try to log in?",
        help_text="Open the Avni app and try entering your username and password.",
        options=[
            TroubleshootOption(label="It says 'Invalid username or password'", next_step_id="wrong_credentials"),
            TroubleshootOption(label="It says 'Network error' or nothing happens", next_step_id="network_error"),
            TroubleshootOption(label="I forgot my password", next_step_id="forgot_password"),
            TroubleshootOption(label="The app crashes when I try to log in", next_step_id="login_crash"),
        ],
    )

    steps["wrong_credentials"] = TroubleshootStep(
        id="wrong_credentials",
        question="Did you check for typing mistakes?",
        help_text=(
            "Common mistakes:\n"
            "- Extra spaces before or after your username\n"
            "- CAPS LOCK is on (passwords are case-sensitive)\n"
            "- Using the wrong email -- check which email your admin registered"
        ),
        options=[
            TroubleshootOption(
                label="I'm sure I typed it correctly",
                solution=(
                    "Your password may have been changed or your account may be disabled.\n\n"
                    "Contact your organisation admin and ask them to:\n"
                    "1. Check if your account is active in the Users section\n"
                    "2. Reset your password\n"
                    "3. Share the new temporary password with you\n\n"
                    "After logging in with the new password, change it to something you can remember."
                ),
            ),
            TroubleshootOption(
                label="Let me try again more carefully",
                solution=(
                    "Tips for entering your login details:\n\n"
                    "1. Tap the 'eye' icon next to the password field to see what you typed\n"
                    "2. Make sure there are no spaces at the beginning or end of your username\n"
                    "3. If your username is an email, type it in lowercase\n"
                    "4. If you copy-pasted the password, make sure no extra spaces were copied"
                ),
            ),
        ],
    )

    steps["network_error"] = TroubleshootStep(
        id="network_error",
        question="Can you open a website (like google.com) in your phone browser?",
        help_text="This checks if your phone has a working internet connection.",
        options=[
            TroubleshootOption(
                label="No, websites don't open either",
                solution=(
                    "You need internet to log in for the first time.\n\n"
                    "1. Turn on WiFi or mobile data\n"
                    "2. Make sure your data plan is active (not expired)\n"
                    "3. Try moving to an area with better signal\n"
                    "4. Try again after connecting\n\n"
                    "Note: After the first login, you can use the app offline and sync later."
                ),
            ),
            TroubleshootOption(
                label="Yes, websites work fine",
                solution=(
                    "The Avni server might be temporarily down. Try:\n\n"
                    "1. Wait 5 minutes and try again\n"
                    "2. Check if the server URL is correct:\n"
                    "   Go to Settings > the URL should be https://app.avniproject.org\n"
                    "3. If the problem continues for more than 30 minutes, contact your admin"
                ),
            ),
        ],
    )

    steps["forgot_password"] = TroubleshootStep(
        id="forgot_password",
        question="",
        help_text="Password resets need to be done by your organisation admin.",
        options=[
            TroubleshootOption(
                label="How do I reset my password?",
                solution=(
                    "Contact your organisation admin (the person who created your Avni account).\n\n"
                    "Ask them to:\n"
                    "1. Log in to https://app.avniproject.org\n"
                    "2. Go to the Users section\n"
                    "3. Find your username\n"
                    "4. Click 'Reset Password'\n"
                    "5. Share the new password with you\n\n"
                    "Once you log in with the new password, it is a good idea to change it "
                    "to something only you know."
                ),
            ),
        ],
    )

    steps["login_crash"] = TroubleshootStep(
        id="login_crash",
        question="Does the app crash immediately or after you tap 'Login'?",
        help_text="If the app closes by itself, that is a crash.",
        options=[
            TroubleshootOption(
                label="It crashes as soon as I open the app",
                solution=(
                    "The app installation may be corrupted. Try:\n\n"
                    "1. Restart your phone\n"
                    "2. Try opening the app again\n\n"
                    "If it still crashes:\n"
                    "3. Uninstall the Avni app\n"
                    "4. Reinstall from the Google Play Store\n"
                    "5. Set the server URL and try logging in again\n\n"
                    "WARNING: Uninstalling will remove any data that has not been synced. "
                    "If you had un-synced data, contact your admin first."
                ),
            ),
            TroubleshootOption(
                label="It crashes after I tap Login",
                solution=(
                    "This can happen if there is too much data to download during first sync.\n\n"
                    "Try:\n"
                    "1. Make sure you are on strong WiFi\n"
                    "2. Close all other apps on your phone\n"
                    "3. Make sure you have at least 1 GB free storage\n"
                    "4. Try logging in again\n\n"
                    "If it keeps crashing, contact your admin -- they may need to reduce "
                    "the data in your catchment area."
                ),
            ),
        ],
    )

    return TroubleshootFlow(
        id="login_problems",
        title="Login problems",
        description="Fix issues logging into the Avni app.",
        category="Login & Authentication",
        steps=steps,
        start_step="start",
    )


def _build_app_crashing_flow() -> TroubleshootFlow:
    """Flow 4: App is crashing."""
    steps: dict[str, TroubleshootStep] = {}

    steps["start"] = TroubleshootStep(
        id="start",
        question="When does the app crash?",
        help_text="A crash means the app suddenly closes by itself.",
        options=[
            TroubleshootOption(label="When I open the app", next_step_id="crash_on_open"),
            TroubleshootOption(label="When I open a specific form or screen", next_step_id="crash_on_form"),
            TroubleshootOption(label="When I try to sync", next_step_id="crash_on_sync"),
            TroubleshootOption(label="The app is very slow but doesn't crash", next_step_id="slow_app"),
        ],
    )

    steps["crash_on_open"] = TroubleshootStep(
        id="crash_on_open",
        question="Did you recently update the app?",
        help_text="Check if the Play Store recently updated Avni automatically.",
        options=[
            TroubleshootOption(
                label="Yes, it was updated recently",
                solution=(
                    "The new version may have an issue. Try:\n\n"
                    "1. Go to Play Store > search 'Avni' > check if another update is available\n"
                    "2. If yes, update again (the issue may have been fixed)\n"
                    "3. If no update available, report this to your admin with:\n"
                    "   - Your phone model (e.g., Samsung Galaxy M12)\n"
                    "   - Android version (Settings > About Phone > Android Version)\n"
                    "   - The Avni app version (shown on login screen)"
                ),
            ),
            TroubleshootOption(
                label="No update or I'm not sure",
                solution=(
                    "Try these steps:\n\n"
                    "1. Restart your phone (turn off and on again)\n"
                    "2. Open Avni again\n\n"
                    "If it still crashes:\n"
                    "3. Clear the app cache:\n"
                    "   Settings > Apps > Avni > Storage > Clear Cache\n"
                    "4. Try again\n\n"
                    "If nothing works:\n"
                    "5. Uninstall and reinstall from Play Store\n"
                    "   (WARNING: Un-synced data will be lost. Contact admin first.)"
                ),
            ),
        ],
    )

    steps["crash_on_form"] = TroubleshootStep(
        id="crash_on_form",
        question="Does it crash on one specific form, or all forms?",
        help_text="Try opening a different form to check.",
        options=[
            TroubleshootOption(
                label="Only one specific form",
                solution=(
                    "That form may have a configuration issue.\n\n"
                    "Tell your admin:\n"
                    "1. The name of the form that crashes\n"
                    "2. The name of the person's profile you were viewing (if applicable)\n"
                    "3. The exact step where it crashes (e.g., when you tap a specific field)\n\n"
                    "The admin should check the form's rules and skip logic in App Designer."
                ),
            ),
            TroubleshootOption(
                label="All forms crash",
                solution=(
                    "This is likely a phone storage or memory issue.\n\n"
                    "1. Free up phone storage:\n"
                    "   - Delete old photos, videos, or unused apps\n"
                    "   - You need at least 500 MB free space\n"
                    "2. Close all other apps running in the background\n"
                    "3. Restart your phone\n"
                    "4. Open only Avni and try again\n\n"
                    "If the problem continues, your phone may not have enough memory (RAM) "
                    "to run the latest version of Avni."
                ),
            ),
        ],
    )

    steps["crash_on_sync"] = TroubleshootStep(
        id="crash_on_sync",
        question="Does the crash happen every time you sync?",
        help_text="Try syncing 2-3 times to see if the crash is consistent.",
        options=[
            TroubleshootOption(
                label="Yes, every time",
                solution=(
                    "There may be a data issue preventing sync. Try:\n\n"
                    "1. Connect to strong WiFi\n"
                    "2. Close all other apps\n"
                    "3. Open Avni and try syncing\n"
                    "4. If it crashes, try resetting sync:\n"
                    "   Settings > Reset Sync\n\n"
                    "If reset sync also crashes, contact your admin. They may need to "
                    "check the server logs for errors related to your account."
                ),
            ),
            TroubleshootOption(
                label="Sometimes it works, sometimes it crashes",
                solution=(
                    "This is usually a network or memory issue.\n\n"
                    "1. Sync only when you have a stable WiFi connection\n"
                    "2. Close all other apps before syncing\n"
                    "3. Make sure your phone is charged (at least 30%)\n"
                    "4. Do not switch away from the Avni app while syncing\n\n"
                    "Try to sync regularly (daily) so that each sync has less data to process."
                ),
            ),
        ],
    )

    steps["slow_app"] = TroubleshootStep(
        id="slow_app",
        question="Is the whole app slow, or only certain screens?",
        help_text="Try navigating to different parts of the app to check.",
        options=[
            TroubleshootOption(
                label="The whole app is slow",
                solution=(
                    "Your phone may be running low on resources.\n\n"
                    "1. Restart your phone\n"
                    "2. Close all other apps\n"
                    "3. Free up storage space (delete old photos, videos, unused apps)\n"
                    "4. Make sure you have the latest version of Avni from Play Store\n\n"
                    "If your phone is old (more than 4-5 years), it may struggle with the app. "
                    "Avni works best on phones with at least 2 GB RAM."
                ),
            ),
            TroubleshootOption(
                label="Only certain screens are slow (like the search screen)",
                solution=(
                    "Screens that show many records (like search or lists) can be slow when "
                    "you have a lot of registered beneficiaries.\n\n"
                    "Tips:\n"
                    "1. Use filters to narrow down results instead of scrolling through all records\n"
                    "2. Search by name instead of browsing the full list\n"
                    "3. Sync regularly so the app stays up to date\n\n"
                    "If a specific screen is very slow, tell your admin the screen name "
                    "and how many records you have. They may be able to optimise it."
                ),
            ),
        ],
    )

    return TroubleshootFlow(
        id="app_crashing",
        title="App is crashing or slow",
        description="Fix issues where the Avni app closes unexpectedly or runs slowly.",
        category="App Performance",
        steps=steps,
        start_step="start",
    )


def _build_cant_find_data_flow() -> TroubleshootFlow:
    """Flow 5: Can't find my data."""
    steps: dict[str, TroubleshootStep] = {}

    steps["start"] = TroubleshootStep(
        id="start",
        question="What data are you looking for?",
        help_text="Tell us what you are trying to find.",
        options=[
            TroubleshootOption(label="A person I registered", next_step_id="find_person"),
            TroubleshootOption(label="A form I filled earlier", next_step_id="find_form_data"),
            TroubleshootOption(label="Data I entered but it disappeared", next_step_id="data_disappeared"),
        ],
    )

    steps["find_person"] = TroubleshootStep(
        id="find_person",
        question="How are you searching for the person?",
        help_text="You can find registered people using the search screen.",
        options=[
            TroubleshootOption(
                label="I searched by name but can't find them",
                solution=(
                    "Try these search tips:\n\n"
                    "1. Check the spelling -- try searching with just the first few letters\n"
                    "2. Make sure you are searching in the right subject type "
                    "(Individual, Household, etc.)\n"
                    "3. The person may be in a different catchment area that you don't have access to\n"
                    "4. Sync your app first, then search again\n\n"
                    "If you just registered this person, their data might not have synced yet. "
                    "Sync your app and check again."
                ),
            ),
            TroubleshootOption(
                label="I don't know how to search",
                solution=(
                    "To find a registered person:\n\n"
                    "1. Open the Avni app\n"
                    "2. Tap the search icon (magnifying glass) at the top\n"
                    "3. Select the type of person you are looking for "
                    "(e.g., Individual, Household)\n"
                    "4. Type the person's name in the search box\n"
                    "5. Tap on the person's name in the results to open their profile\n\n"
                    "You can also browse by location using the lists on the home screen."
                ),
            ),
        ],
    )

    steps["find_form_data"] = TroubleshootStep(
        id="find_form_data",
        question="Where did you fill the form?",
        help_text="Forms are linked to specific people and visits.",
        options=[
            TroubleshootOption(
                label="During a visit to a person",
                solution=(
                    "To find the data you entered during a visit:\n\n"
                    "1. Search for and open the person's profile\n"
                    "2. Look under 'Visits' or 'Encounters'\n"
                    "3. Find the visit by date\n"
                    "4. Tap on the visit to see the form data you entered\n\n"
                    "If the visit does not show up:\n"
                    "- Sync your app and check again\n"
                    "- You may have saved it as a draft -- check the 'Drafts' section"
                ),
            ),
            TroubleshootOption(
                label="During registration",
                solution=(
                    "Registration data is on the person's profile:\n\n"
                    "1. Search for the person\n"
                    "2. Open their profile\n"
                    "3. The registration details are shown at the top of their profile\n"
                    "4. Tap 'Edit' or the pencil icon to see all registration fields"
                ),
            ),
        ],
    )

    steps["data_disappeared"] = TroubleshootStep(
        id="data_disappeared",
        question="Did you sync before the data disappeared?",
        help_text="Data that is not synced is only saved on your phone.",
        options=[
            TroubleshootOption(
                label="Yes, I synced and then data went missing",
                solution=(
                    "This is unusual. The data might have been modified by another user, "
                    "or there may be a sync conflict.\n\n"
                    "1. Try syncing again to get the latest data\n"
                    "2. Check if another field worker has access to the same person "
                    "-- they may have edited the record\n"
                    "3. If data is truly missing, contact your admin immediately\n"
                    "   They can check the server audit logs to see what happened"
                ),
            ),
            TroubleshootOption(
                label="I did not sync / I'm not sure",
                solution=(
                    "If you did not sync, your data is still on your phone. Try:\n\n"
                    "1. DO NOT uninstall the app or clear app data\n"
                    "2. Open Avni and search for the person you entered data for\n"
                    "3. Check the Drafts section -- your form may be saved as a draft\n"
                    "4. Sync your app to upload the data to the server\n\n"
                    "Important: Always sync after entering data. Un-synced data only exists "
                    "on your phone and can be lost if the app is uninstalled."
                ),
            ),
        ],
    )

    return TroubleshootFlow(
        id="cant_find_data",
        title="Can't find my data",
        description="Find registered people, forms, or data that seems to be missing.",
        category="Forms & Data",
        steps=steps,
        start_step="start",
    )


def _build_report_wrong_flow() -> TroubleshootFlow:
    """Flow 6: Report is wrong."""
    steps: dict[str, TroubleshootStep] = {}

    steps["start"] = TroubleshootStep(
        id="start",
        question="What is wrong with the report?",
        help_text="Reports show summary data based on your synced records.",
        options=[
            TroubleshootOption(label="The numbers don't look right", next_step_id="wrong_numbers"),
            TroubleshootOption(label="The report is blank or not loading", next_step_id="blank_report"),
            TroubleshootOption(label="I can't find the report I need", next_step_id="report_missing"),
        ],
    )

    steps["wrong_numbers"] = TroubleshootStep(
        id="wrong_numbers",
        question="Did you sync your app recently?",
        help_text="Reports on the web use synced data. If you haven't synced, recent entries won't appear.",
        options=[
            TroubleshootOption(
                label="Yes, I synced today",
                solution=(
                    "If numbers still look wrong after syncing:\n\n"
                    "1. Check the date range -- reports may be showing a different time period "
                    "than you expect\n"
                    "2. Check the filters -- you may have a location or program filter active\n"
                    "3. Some reports update once a day (not in real-time)\n"
                    "4. Compare with a colleague -- ask them to check the same report\n\n"
                    "If you are sure the numbers are wrong, contact your admin with:\n"
                    "- The report name\n"
                    "- What number you see vs. what you expect\n"
                    "- The date range and filters you used"
                ),
            ),
            TroubleshootOption(
                label="No, I haven't synced recently",
                solution=(
                    "That is likely why the numbers are off.\n\n"
                    "1. Open the Avni app\n"
                    "2. Sync your data (make sure it completes fully)\n"
                    "3. Wait a few minutes\n"
                    "4. Check the report again on the web\n\n"
                    "Ask your team members to sync their apps too. "
                    "If multiple people have un-synced data, reports will be incomplete."
                ),
            ),
        ],
    )

    steps["blank_report"] = TroubleshootStep(
        id="blank_report",
        question="Are you viewing the report on the web or in the app?",
        help_text="Most reports are viewed on the Avni web portal.",
        options=[
            TroubleshootOption(
                label="On the web portal",
                solution=(
                    "Try these steps:\n\n"
                    "1. Refresh the page (press Ctrl+R or F5)\n"
                    "2. Clear your browser cache (Ctrl+Shift+Delete)\n"
                    "3. Try a different browser (Chrome usually works best)\n"
                    "4. Check if you have the right permissions to view reports\n\n"
                    "If the report still won't load, contact your admin. The report "
                    "configuration may need to be checked."
                ),
            ),
            TroubleshootOption(
                label="In the Avni app",
                solution=(
                    "In-app reports need synced data.\n\n"
                    "1. Make sure you have synced recently\n"
                    "2. Check that you have registered at least some people in your catchment\n"
                    "3. Some reports only appear after a minimum number of records exist\n\n"
                    "If the report is still blank, it may not be configured for your organisation. "
                    "Ask your admin."
                ),
            ),
        ],
    )

    steps["report_missing"] = TroubleshootStep(
        id="report_missing",
        question="",
        help_text="Different users may have access to different reports.",
        options=[
            TroubleshootOption(
                label="How do I find the right report?",
                solution=(
                    "To find reports:\n\n"
                    "On the web:\n"
                    "1. Log in to https://app.avniproject.org\n"
                    "2. Click 'Reports' in the menu\n"
                    "3. Browse the available reports\n"
                    "4. Use filters to narrow down by date range, location, etc.\n\n"
                    "In the app:\n"
                    "1. Open the Avni app\n"
                    "2. Look for a 'Reports' tab at the bottom\n\n"
                    "If you don't see the report you need, ask your admin to:\n"
                    "- Check if the report exists\n"
                    "- Give you access to view it"
                ),
            ),
        ],
    )

    return TroubleshootFlow(
        id="report_wrong",
        title="Report is wrong or missing",
        description="Fix issues with reports showing incorrect data or not loading.",
        category="Reports",
        steps=steps,
        start_step="start",
    )


def _build_export_data_flow() -> TroubleshootFlow:
    """Flow 7: How to export data."""
    steps: dict[str, TroubleshootStep] = {}

    steps["start"] = TroubleshootStep(
        id="start",
        question="What data do you want to export?",
        help_text="Avni allows exporting data in different formats.",
        options=[
            TroubleshootOption(label="Registration data (list of all registered people)", next_step_id="export_registration"),
            TroubleshootOption(label="Visit/encounter data (form data from visits)", next_step_id="export_encounters"),
            TroubleshootOption(label="I just want to share one person's details", next_step_id="share_single"),
        ],
    )

    steps["export_registration"] = TroubleshootStep(
        id="export_registration",
        question="Do you have access to the Avni web portal?",
        help_text="Data export is done from the web portal (https://app.avniproject.org), not the phone app.",
        options=[
            TroubleshootOption(
                label="Yes, I can log in to the web portal",
                solution=(
                    "To export registration data:\n\n"
                    "1. Log in to https://app.avniproject.org\n"
                    "2. Click 'Reports' in the top menu\n"
                    "3. Look for an 'Export' option or a 'Download' button\n"
                    "4. Select the subject type you want to export\n"
                    "5. Choose your filters (date range, location, etc.)\n"
                    "6. Click 'Export' or 'Download'\n"
                    "7. The file will download as an Excel/CSV file\n\n"
                    "Note: You need admin or data export privileges to use this feature. "
                    "If you don't see the export option, ask your admin."
                ),
            ),
            TroubleshootOption(
                label="No, I only use the phone app",
                solution=(
                    "Data export is only available from the web portal.\n\n"
                    "You have two options:\n"
                    "1. Ask your admin to export the data for you and share the file\n"
                    "2. Ask your admin to give you web portal access so you can export yourself\n\n"
                    "To log in to the web portal, you need a computer or can use your phone's "
                    "browser at https://app.avniproject.org (use the same login credentials)."
                ),
            ),
        ],
    )

    steps["export_encounters"] = TroubleshootStep(
        id="export_encounters",
        question="Do you want to export data for all people or just one person?",
        help_text="",
        options=[
            TroubleshootOption(
                label="All people (bulk export)",
                solution=(
                    "For bulk encounter data export:\n\n"
                    "1. Log in to the Avni web portal\n"
                    "2. Go to Reports > Export\n"
                    "3. Select the encounter type you want to export\n"
                    "4. Choose your date range and location filters\n"
                    "5. Click Export\n\n"
                    "The export may take a few minutes if you have many records. "
                    "You will get an Excel/CSV file with all the form data.\n\n"
                    "If you cannot see the export option, you need admin privileges."
                ),
            ),
            TroubleshootOption(
                label="Just one person",
                next_step_id="share_single",
            ),
        ],
    )

    steps["share_single"] = TroubleshootStep(
        id="share_single",
        question="",
        help_text="You can view and note down a single person's details from the app.",
        options=[
            TroubleshootOption(
                label="How do I do this?",
                solution=(
                    "To view and share one person's data:\n\n"
                    "From the app:\n"
                    "1. Search for the person\n"
                    "2. Open their profile\n"
                    "3. You can see all their registration details and visit history\n"
                    "4. Take a screenshot to share: press Power + Volume Down buttons together\n\n"
                    "From the web portal:\n"
                    "1. Search for the person\n"
                    "2. Open their profile\n"
                    "3. You can print the page or copy the information\n\n"
                    "Note: Be careful sharing personal data. Follow your organisation's "
                    "data privacy guidelines."
                ),
            ),
        ],
    )

    return TroubleshootFlow(
        id="export_data",
        title="How to export data",
        description="Learn how to download or share data from Avni.",
        category="Reports",
        steps=steps,
        start_step="start",
    )


# ---------------------------------------------------------------------------
# Flow registry
# ---------------------------------------------------------------------------

_FLOWS: dict[str, TroubleshootFlow] = {}


def _init_flows() -> None:
    """Populate the flow registry. Called once on first access."""
    if _FLOWS:
        return

    builders = [
        _build_sync_flow,
        _build_form_not_showing_flow,
        _build_login_problems_flow,
        _build_app_crashing_flow,
        _build_cant_find_data_flow,
        _build_report_wrong_flow,
        _build_export_data_flow,
    ]

    for builder in builders:
        flow = builder()
        _FLOWS[flow.id] = flow

    logger.info("Initialised %d troubleshooting flows", len(_FLOWS))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_flows() -> list[TroubleshootFlow]:
    """Return all troubleshooting flows."""
    _init_flows()
    return list(_FLOWS.values())


def get_flow(flow_id: str) -> TroubleshootFlow | None:
    """Return a specific flow by ID, or None if not found."""
    _init_flows()
    return _FLOWS.get(flow_id)


def get_step(flow_id: str, step_id: str) -> TroubleshootStep | None:
    """Return a specific step within a flow, or None if not found."""
    _init_flows()
    flow = _FLOWS.get(flow_id)
    if flow is None:
        return None
    return flow.steps.get(step_id)


def search_flows(query: str) -> list[TroubleshootFlow]:
    """Search flows by keyword matching against title, description, and step text.

    Returns flows sorted by relevance (number of keyword matches).
    """
    _init_flows()

    if not query or not query.strip():
        return list(_FLOWS.values())

    keywords = query.lower().split()
    scored: list[tuple[int, TroubleshootFlow]] = []

    for flow in _FLOWS.values():
        score = 0
        searchable = (
            f"{flow.title} {flow.description} {flow.category}"
        ).lower()

        # Also include step questions and solutions for deeper matching
        for step in flow.steps.values():
            searchable += f" {step.question} {step.help_text}"
            for option in step.options:
                searchable += f" {option.label}"
                if option.solution:
                    searchable += f" {option.solution}"

        for kw in keywords:
            if kw in searchable:
                score += searchable.count(kw)

        if score > 0:
            scored.append((score, flow))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [flow for _, flow in scored]
