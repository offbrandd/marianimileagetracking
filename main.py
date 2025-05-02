import csv
import sys
import os
from datetime import datetime
from typing import Optional, Tuple # For type hinting

# --- PySide6 Imports ---
from PySide6.QtCore import QSize, QObject, Qt
from PySide6.QtGui import QIcon, QAction, QCloseEvent # Added QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QPushButton,
    QButtonGroup, QVBoxLayout, QInputDialog, QSystemTrayIcon, QMenu,
    QMessageBox
)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # sys._MEIPASS is deprecated, use sys.executable and handle frozen state
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            # Not bundled, running in development mode
            # Use the directory of the main script file
            base_path = os.path.abspath(os.path.dirname(__file__))
    except Exception:
        # Fallback to current working directory if other methods fail
         base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# --- Configuration Constants ---
# Using uppercase for constants is standard Python practice
LOCATIONS = {
    '505': '5',
    'Baker/Edwards/HR': '1',
    'Buckeye': '7'
}
FILENAME = 'trips.csv'
ICON_PATH = resource_path("mariani_icon.png")
# Use a constant for notification duration (3000ms = 3 seconds)
# 100ms was too short and likely ignored by the OS anyway
NOTIFICATION_DURATION_MS = 3000

# --- CSV Initialization ---
def initialize_csv(filename: str) -> None:
    """Creates the CSV file with headers if it doesn't exist."""
    if not os.path.exists(filename):
        try:
            with open(filename, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Date", "Location", "Number"])
        except IOError as e:
            # Keep critical error reporting, use MessageBox for UI feedback
            critical_message = f"Could not create required file '{filename}': {e}"
            print(f"CRITICAL ERROR: {critical_message}") # Log critical error to console
            # Show message box before exiting (though app hasn't started fully)
            temp_app = QApplication.instance() # Check if app exists
            if not temp_app:
                temp_app = QApplication(sys.argv) # Create temp if needed for msgbox
            QMessageBox.critical(None, "Fatal Error", critical_message)
            sys.exit(1) # Exit if we can't create the essential file

# --- Core Data Functions ---
def add_trip_record(location: str) -> None:
    """
    Appends a trip record for a predefined location to the CSV file.
    Raises IOError on file write errors.
    Raises KeyError if location is invalid.
    """
    entry = [datetime.now().strftime("%Y-%m-%d"), location, LOCATIONS[location]]
    # 'with open' handles closing, raises IOError if write fails
    with open(FILENAME, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(entry)

def get_custom_trip_input(parent_window: QWidget) -> Tuple[bool, Optional[str]]:
    """
    Shows dialogs to get custom trip details and adds the record to the CSV.
    Returns a tuple: (success_boolean, message_details_string_or_None).
    Handles user cancellations and file write errors via message boxes.
    """
    location_name, ok1 = QInputDialog.getText(parent_window, "Custom Trip Input",
                                             "Enter Location Name:")

    if ok1 and location_name:
        number_str, ok2 = QInputDialog.getText(parent_window, "Custom Trip Input",
                                              f"Enter Number for '{location_name}':")

        if ok2 and number_str:
            entry = [datetime.now().strftime("%Y-%m-%d"), location_name, number_str]
            try:
                with open(FILENAME, 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(entry)
                # Return success and details for the notification message
                return True, f"{location_name} ({number_str} mi)"
            except IOError as e:
                QMessageBox.warning(parent_window, "File Error",
                                    f"Could not write trip to {FILENAME}:\n{e}")
                return False, None # Indicate failure

        elif ok2: # User pressed OK but left number empty
             QMessageBox.information(parent_window, "Input Required",
                                     "Custom trip number cannot be empty.")
    elif ok1: # User pressed OK but left location empty
         QMessageBox.information(parent_window, "Input Required",
                                 "Location name cannot be empty.")

    # Return failure if any dialog was cancelled or input was invalid
    return False, None


# --- Main Window Class ---
class MainWindow(QMainWindow):
    """Main application window for selecting trip types."""
    def __init__(self) -> None:
        super().__init__()
        self.tray_manager: Optional[TrayManager] = None # Type hint for clarity

        self.setWindowTitle("Trip Logger")
        self.resize(QSize(300, 250)) # Initial size

        button_group = QButtonGroup(self)
        layout = QVBoxLayout()

        # Define buttons based on LOCATIONS dictionary keys
        for location_name in LOCATIONS.keys():
            button = QPushButton(location_name) # Button label is the location name
            button_group.addButton(button)
            # Use lambda to pass the specific location name when clicked
            button.clicked.connect(lambda checked=False, loc=location_name: self.add_predefined_trip(loc))
            layout.addWidget(button)

        # --- Custom Trip Button ---
        custom_button = QPushButton("Custom Trip")
        button_group.addButton(custom_button)
        custom_button.clicked.connect(self.add_custom_trip)
        layout.addWidget(custom_button)

        # --- Set Layout ---
        main_container = QWidget()
        main_container.setLayout(layout)
        self.setCentralWidget(main_container)

    def set_tray_manager(self, manager: 'TrayManager') -> None:
        """Stores a reference to the TrayManager instance for notifications."""
        self.tray_manager = manager

    def add_predefined_trip(self, location: str) -> None:
        """Handles adding a predefined trip and notifying the user."""
        try:
            # Add the record to the CSV
            add_trip_record(location)

            # Notify via tray manager if it's available
            if self.tray_manager:
                mileage = LOCATIONS[location] # Get mileage for notification
                self.tray_manager.show_notification(f"Added trip to {location} ({mileage} mi)")

        except IOError as e:
            QMessageBox.warning(self, "File Error", f"Could not write trip to {FILENAME}:\n{e}")
        except KeyError: # Should not happen if buttons are generated from LOCATIONS keys
             QMessageBox.critical(self, "Configuration Error",
                                  f"Internal error: Location '{location}' not configured correctly.")
        except Exception as e: # Catch any other unexpected errors during the process
            QMessageBox.critical(self, "Unexpected Error", f"An unexpected error occurred:\n{e}")

    def add_custom_trip(self) -> None:
        """Handles adding a custom trip and notifying the user."""
        # get_custom_trip_input handles dialogs, CSV writing, and basic error reporting
        success, details = get_custom_trip_input(self)

        if success and self.tray_manager:
            # Notify via tray manager if successful and manager exists
            self.tray_manager.show_notification(f"Added custom trip: {details}")
        # No automatic hiding; window stays open unless user closes/minimizes

    def closeEvent(self, event: QCloseEvent) -> None:
        """Overrides the window close event (clicking 'X') to hide the window."""
        event.ignore() # Prevent the application from quitting
        self.hide()    # Hide the main window
        # Optionally notify that it's still running (briefly)
        if self.tray_manager:
             self.tray_manager.tray.showMessage(
                 "Still Running",
                 "Trip Logger is running in the system tray.",
                 QSystemTrayIcon.MessageIcon.Information,
                 1500 # Slightly longer duration for this specific info message
             )


# --- System Tray Class ---
class TrayManager(QObject):
    """Manages the system tray icon, menu, and notifications."""
    def __init__(self, application: QApplication, main_window: MainWindow, app_icon: QIcon, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.app = application
        self.main_window = main_window
        self.icon = app_icon # Use the icon loaded globally

        # --- Create Tray Icon ---
        self.tray = QSystemTrayIcon(self.icon, parent=self)
        self.tray.setToolTip("Trip Logger")

        # --- Create Menu ---
        self.menu = QMenu()
        show_action = QAction("Show Logger Window", self)
        # Ensure window is shown and brought to the front
        show_action.triggered.connect(self.main_window.show)
        show_action.triggered.connect(self.main_window.activateWindow)
        self.menu.addAction(show_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit Trip Logger", self)
        # Connect to the application's quit slot for proper cleanup
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)

        # --- Final Tray Setup ---
        self.tray.setContextMenu(self.menu)
        self.tray.setVisible(True)
        self.tray.activated.connect(self.on_tray_icon_activated)

    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Shows the main window when the tray icon is clicked."""
        # QSystemTrayIcon.ActivationReason.Trigger corresponds to a normal click
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.main_window.show()
            self.main_window.activateWindow() # Bring it to the front

    def show_notification(self, message: str) -> None:
        """Displays a standard notification message from the system tray icon."""
        self.tray.showMessage(
            "Trip Added Successfully",
            message,
            QSystemTrayIcon.MessageIcon.Information,
            NOTIFICATION_DURATION_MS # Use the defined constant
        )

# --- Main Execution Block ---
if __name__ == "__main__":
    # Ensure the CSV file exists before starting the application
    initialize_csv(FILENAME)

    # --- Application Setup ---
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Keep running when window is hidden

    # --- Load and Set Application Icon ---
    if os.path.exists(ICON_PATH):
        app_icon = QIcon(ICON_PATH)
    else:
        # Log warning to console if icon is missing
        print(f"Warning: Icon file not found at {ICON_PATH}. Using default application icon.")
        app_icon = QIcon.fromTheme("application-x-executable") # Fallback icon

    app.setWindowIcon(app_icon)

    # --- Create UI Components ---
    window = MainWindow()
    tray_manager = TrayManager(app, window, app_icon)

    # --- Link Components ---
    # Provide the window with a way to access the tray manager for notifications
    window.set_tray_manager(tray_manager)

    # --- Show Initial Window ---
    window.show()

    # --- Start Event Loop ---
    sys.exit(app.exec()) # Execute and handle exit code