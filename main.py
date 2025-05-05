import csv
import sys
import os
from datetime import datetime
from typing import Optional, Tuple, List # Added List

# --- PySide6 Imports ---
from PySide6.QtCore import QSize, QObject, Qt, QSettings, QStandardPaths # Added QSettings, QStandardPaths
from PySide6.QtGui import QIcon, QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QPushButton,
    QButtonGroup, QVBoxLayout, QInputDialog, QSystemTrayIcon, QMenu,
    QMessageBox, QFileDialog # Added QFileDialog
)

# --- Configuration Constants ---
ORGANIZATION_NAME = "Mariani Nut Co - Brandon Tytler" # Replace with yours
APPLICATION_NAME = "TripLogger"
LOCATIONS = {
    '505': '5',
    'Baker/Edwards/HR': '1',
    'Buckeye': '7'
}
# FILENAME is now dynamic, defined later using QSettings
ICON_FILENAME = "mariani_icon.png" # Base name for the icon file
NOTIFICATION_DURATION_MS = 1000

# --- Helper function for resource path ---
def resource_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # PyInstaller temp folder
            base_path = sys._MEIPASS
        else:
            # Development mode
            base_path = os.path.abspath(os.path.dirname(__file__))
    except Exception:
         base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Define Icon Path using the helper
ICON_PATH = resource_path(ICON_FILENAME)

# --- Settings Functions ---
def save_data_file_path(path: Optional[str]) -> None:
    """Saves the chosen data file path to settings. Saves empty string if path is None."""
    settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
    settings.setValue("dataFilePath", path if path else "") # Store empty string for None

def load_data_file_path() -> Optional[str]:
    """Loads the data file path from settings. Returns None if not set or empty."""
    settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
    path = settings.value("dataFilePath")
    # Return None if path is None or an empty string
    return path if path else None

# --- CSV File Handling ---
def initialize_csv(filename: str) -> bool:
    """Creates the CSV file with headers if it doesn't exist at the given path."""
    if not filename: # Cannot initialize if filename is empty/None
        return False
    directory = os.path.dirname(filename)
    try:
        if directory: # Only create if directory part exists (might be just filename)
             os.makedirs(directory, exist_ok=True)
    except OSError as e:
         QMessageBox.critical(None, "Directory Error", f"Could not create directory:\n{directory}\nError: {e}")
         return False

    if not os.path.exists(filename):
        try:
            with open(filename, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Date", "Location", "Number"])
            return True
        except IOError as e:
            QMessageBox.critical(None, "File Creation Error", f"Could not create required file:\n{filename}\nError: {e}")
            return False
    # Check if we can write to existing file (simple permission check)
    try:
        with open(filename, 'a', newline=''):
            pass
        return True
    except IOError as e:
        QMessageBox.critical(None, "File Access Error", f"Cannot write to selected file (check permissions):\n{filename}\nError: {e}")
        return False


# --- Core Data Functions (now require file_path argument) ---
def add_trip_record(location: str, file_path: str) -> None:
    """Appends a trip record to the specified CSV file."""
    entry = [datetime.now().strftime("%Y-%m-%d"), location, LOCATIONS[location]]
    with open(file_path, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(entry)

def get_custom_trip_input(parent_window: QWidget, file_path: str) -> Tuple[bool, Optional[str]]:
    """Gets custom trip details and adds the record to the specified CSV file."""
    location_name, ok1 = QInputDialog.getText(parent_window, "Custom Trip Input", "Enter Location Name:")
    if ok1 and location_name:
        number_str, ok2 = QInputDialog.getText(parent_window, "Custom Trip Input", f"Enter Number for '{location_name}':")
        if ok2 and number_str:
            entry = [datetime.now().strftime("%Y-%m-%d"), location_name, number_str]
            try:
                with open(file_path, 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(entry)
                return True, f"{location_name} ({number_str} mi)"
            except IOError as e:
                QMessageBox.warning(parent_window, "File Error", f"Could not write trip to {os.path.basename(file_path)}:\n{e}")
                return False, None
        elif ok2:
             QMessageBox.information(parent_window, "Input Required", "Custom trip number cannot be empty.")
    elif ok1:
         QMessageBox.information(parent_window, "Input Required", "Location name cannot be empty.")
    return False, None


# --- Main Window Class ---
class MainWindow(QMainWindow):
    """Main application window for selecting trip types."""
    def __init__(self) -> None:
        super().__init__()
        self.tray_manager: Optional[TrayManager] = None
        self.data_file_path: Optional[str] = None # Holds the current path

        self.setWindowTitle("Trip Logger")
        self.resize(QSize(300, 250))

        # --- UI Elements ---
        self.button_group = QButtonGroup(self)
        layout = QVBoxLayout()
        self.trip_buttons: List[QPushButton] = [] # Keep track of buttons

        location_buttons_config = {
             '505': '505',
             'Baker/Edwards/HR': 'Baker/Edwards/HR',
             'Buckeye': 'Buckeye'
        }
        for data_location, button_label in location_buttons_config.items():
            button = QPushButton(button_label)
            self.button_group.addButton(button)
            button.clicked.connect(lambda checked=False, loc=data_location: self.add_predefined_trip(loc))
            layout.addWidget(button)
            self.trip_buttons.append(button)

        custom_button = QPushButton("Custom Trip")
        self.button_group.addButton(custom_button)
        custom_button.clicked.connect(self.add_custom_trip)
        layout.addWidget(custom_button)
        self.trip_buttons.append(custom_button)

        main_container = QWidget()
        main_container.setLayout(layout)
        self.setCentralWidget(main_container)

        # --- Setup Menu ---
        self._create_menus()

        # --- Load Settings and Check Path ---
        self.load_settings_and_update_state()
    
    # --- Add this method back inside the MainWindow class ---
    def set_tray_manager(self, manager: 'TrayManager') -> None:
        """Stores a reference to the TrayManager instance for notifications."""
        # Type hint uses forward reference string 'TrayManager' as the class might be defined later
        self.tray_manager = manager

    def _create_menus(self) -> None:
        """Creates the main menu bar and actions."""
        self.set_file_action = QAction("&Set Data File...", self) # Added mnemonic
        self.set_file_action.setStatusTip("Choose the CSV file where trip data will be saved")
        self.set_file_action.triggered.connect(self.prompt_and_set_data_file)

        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.set_file_action)
        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(quit_action)

    def load_settings_and_update_state(self) -> None:
        """Loads the data file path from settings and updates UI state."""
        loaded_path = load_data_file_path()
        is_path_valid = False
        if loaded_path:
            # Check if directory exists and file can be initialized (created/opened)
            if os.path.exists(os.path.dirname(loaded_path)) and initialize_csv(loaded_path):
                 self.data_file_path = loaded_path
                 is_path_valid = True
            else:
                 # Path exists in settings but isn't valid anymore (e.g., dir deleted, no permissions)
                 self.data_file_path = None
                 # Clear the invalid setting
                 save_data_file_path(None)
                 QMessageBox.warning(self, "Invalid Path", f"The previously saved data path is invalid or inaccessible:\n{loaded_path}\nPlease set a new data file location.")
        else:
             self.data_file_path = None

        self.update_button_states(enable=is_path_valid)

        # Prompt user immediately on first run if no valid path is set
        if not is_path_valid:
             self.prompt_for_initial_data_file()


    def prompt_for_initial_data_file(self):
         """Shows a message and triggers the file dialog on first run / invalid path."""
         reply = QMessageBox.information(
              self,
              "Setup Required",
              "Welcome to Trip Logger!\n\nPlease select a location to save your trip data (trips.csv).",
              QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
              )
         if reply == QMessageBox.StandardButton.Ok:
              self.prompt_and_set_data_file()
         # else: User cancelled initial setup, buttons remain disabled


    def prompt_and_set_data_file(self) -> bool:
        """Shows dialog to select/create CSV, saves path, and updates state."""
        documents_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        current_dir = os.path.dirname(self.data_file_path) if self.data_file_path else documents_path
        default_name = os.path.basename(self.data_file_path) if self.data_file_path else "trips.csv"
        suggested_path = os.path.join(current_dir, default_name)


        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Select or Create Data File",
            suggested_path,
            "CSV Files (*.csv);;All Files (*)"
        )

        if file_path:
            if not file_path.lower().endswith(".csv"):
                file_path += ".csv"

            if initialize_csv(file_path): # Checks writability and creates header
                self.data_file_path = file_path
                save_data_file_path(self.data_file_path)
                self.update_button_states(enable=True)
                self.statusBar().showMessage(f"Data file set to: {self.data_file_path}", 5000) # Show in status bar
                return True
            else:
                # initialize_csv showed error message
                self.data_file_path = None
                save_data_file_path(None)
                self.update_button_states(enable=False)
                return False
        else: # User cancelled
             # self.statusBar().showMessage("Data file selection cancelled.", 3000)
             return False

    def update_button_states(self, enable: bool) -> None:
        """Enables or disables the trip adding buttons."""
        for button in self.trip_buttons:
             button.setEnabled(enable)
        if not enable:
             self.statusBar().showMessage("No valid data file set. Use File -> Set Data File...", 0) # Persistent message

    def _is_path_valid(self) -> bool:
         """Checks if data path is set and file is accessible."""
         if not self.data_file_path:
              QMessageBox.warning(self, "Setup Required", "Please set the data file location first using the File menu.")
              # Trigger the prompt maybe?
              # return self.prompt_and_set_data_file()
              return False
         # Re-check writability just in case
         if not initialize_csv(self.data_file_path):
             # Error message shown by initialize_csv
             self.update_button_states(False) # Disable buttons if path becomes invalid
             return False
         return True


    def add_predefined_trip(self, location: str) -> None:
        """Handles adding a predefined trip after checking path."""
        if not self._is_path_valid():
            return

        try:
            # Pass the currently configured path
            add_trip_record(location, self.data_file_path)
            if self.tray_manager:
                mileage = LOCATIONS[location]
                self.tray_manager.show_notification(f"Added trip to {location} ({mileage} mi)")
        except IOError as e:
            QMessageBox.warning(self, "File Error", f"Could not write trip:\n{e}")
            self.update_button_states(False) # Disable buttons if path is unwritable
        except KeyError:
             QMessageBox.critical(self, "Configuration Error", f"Internal error: Location '{location}' not configured.")
        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error", f"An unexpected error occurred:\n{e}")

    def add_custom_trip(self) -> None:
        """Handles adding a custom trip after checking path."""
        if not self._is_path_valid():
            return

        # Pass the currently configured path
        success, details = get_custom_trip_input(self, self.data_file_path)

        if success and self.tray_manager:
             self.tray_manager.show_notification(f"Added custom trip: {details}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Overrides the window close event (clicking 'X') to hide the window."""
        event.ignore()
        self.hide()
        if self.tray_manager:
             self.tray_manager.tray.showMessage( "Still Running",
                 "Trip Logger is running in the system tray.",
                 QSystemTrayIcon.MessageIcon.Information, 1500 )

    # Need this method for TrayManager to access the action
    def get_set_file_action(self) -> QAction:
         return self.set_file_action


# --- System Tray Class ---
class TrayManager(QObject):
    """Manages the system tray icon, menu, and notifications."""
    def __init__(self, application: QApplication, main_window: MainWindow, app_icon: QIcon, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.app = application
        self.main_window = main_window
        self.icon = app_icon

        self.tray = QSystemTrayIcon(self.icon, parent=self)
        self.tray.setToolTip(APPLICATION_NAME) # Use constant

        # --- Create Menu ---
        self.menu = QMenu()

        show_action = QAction("Show Logger Window", self)
        show_action.triggered.connect(self.main_window.show)
        show_action.triggered.connect(self.main_window.activateWindow)
        self.menu.addAction(show_action)

        # Add "Set Data File" Action using the one from MainWindow
        self.menu.addAction(self.main_window.get_set_file_action())

        self.menu.addSeparator()

        quit_action = QAction("Quit Trip Logger", self)
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)

        # --- Final Tray Setup ---
        self.tray.setContextMenu(self.menu)
        self.tray.setVisible(True)
        self.tray.activated.connect(self.on_tray_icon_activated)

    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Shows the main window when the tray icon is clicked."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.main_window.show()
            self.main_window.activateWindow()

    def show_notification(self, message: str) -> None:
        """Displays a standard notification message from the system tray icon."""
        self.tray.showMessage(
            "Trip Added Successfully", message,
            QSystemTrayIcon.MessageIcon.Information, NOTIFICATION_DURATION_MS )


# --- Main Execution Block ---
if __name__ == "__main__":
    # Set Org/App names *before* creating QApplication or QSettings instances
    QApplication.setOrganizationName(ORGANIZATION_NAME)
    QApplication.setApplicationName(APPLICATION_NAME)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # --- Load Icon ---
    if os.path.exists(ICON_PATH):
        app_icon = QIcon(ICON_PATH)
    else:
        print(f"Warning: Icon file not found at resolved path {ICON_PATH}.")
        app_icon = QIcon.fromTheme("application-x-executable")
    app.setWindowIcon(app_icon)

    # --- Create UI Components ---
    # MainWindow now handles loading settings and initial path check
    window = MainWindow()
    tray_manager = TrayManager(app, window, app_icon)
    window.set_tray_manager(tray_manager) # Still needed for notifications

    # --- Show Window ---
    window.show()

    # --- Start Event Loop ---
    sys.exit(app.exec())