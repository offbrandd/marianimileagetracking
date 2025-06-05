import csv
import sys
import os
from datetime import datetime
from typing import Optional, Tuple, List

# --- PySide6 Imports ---
from PySide6.QtCore import QSize, QObject, Qt, QSettings, QStandardPaths, QSharedMemory
from PySide6.QtGui import QIcon, QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QPushButton,
    QButtonGroup, QVBoxLayout, QInputDialog, QSystemTrayIcon, QMenu,
    QMessageBox, QFileDialog
)

# --- Configuration Constants ---
ORGANIZATION_NAME = "Mariani Nut Co - Brandon Tytler" # Replace with yours
APPLICATION_NAME = "TripLogger"
SHARED_MEM_KEY = f"{ORGANIZATION_NAME}_{APPLICATION_NAME}_InstanceLock"

# Updated LOCATIONS: Baker, Edwards, HR are now separate
LOCATIONS = {
    '505': '5',
    'Baker': '1',  # Assuming '1' was the shared mileage, adjust if needed
    'Edwards': '1', # Assuming '1' was the shared mileage, adjust if needed
    'HR': '1',      # Assuming '1' was the shared mileage, adjust if needed
    'Buckeye': '7'
}
ICON_FILENAME = "mariani_icon.png"
NOTIFICATION_DURATION_MS = 1000

# --- Helper function for resource path ---
def resource_path(relative_path: str) -> str:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

ICON_PATH = resource_path(ICON_FILENAME) if os.path.exists(resource_path(ICON_FILENAME)) else QIcon.fromTheme("application-x-executable").name()


# --- Settings Functions ---
def save_data_file_path(path: Optional[str]) -> None:
    """Saves the chosen data file path to settings. Saves empty string if path is None."""
    settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
    settings.setValue("dataFilePath", path if path else "")

def load_data_file_path() -> Optional[str]:
    """Loads the data file path from settings. Returns None if not set or empty."""
    settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
    path = settings.value("dataFilePath")
    return path if path else None

# --- CSV File Handling ---
def initialize_csv(filename: str) -> bool:
    """Creates the CSV file with headers (including Trip Reason) if it doesn't exist."""
    if not filename:
        return False
    directory = os.path.dirname(filename)
    try:
        if directory:
             os.makedirs(directory, exist_ok=True)
    except OSError as e:
         QMessageBox.critical(None, "Directory Error", f"Could not create directory:\n{directory}\nError: {e}")
         return False

    if not os.path.exists(filename):
        try:
            with open(filename, 'w', newline='') as file:
                writer = csv.writer(file)
                # Added "Trip Reason" to header
                writer.writerow(["Date", "Location", "Miles", "Trip Reason"])
            return True
        except IOError as e:
            QMessageBox.critical(None, "File Creation Error", f"Could not create required file:\n{filename}\nError: {e}")
            return False
    else: # File exists, check if header needs update (simple check for "Trip Reason")
        try:
            with open(filename, 'r+', newline='') as file:
                reader = csv.reader(file)
                try:
                    header = next(reader)
                    if len(header) < 4 or header[3].lower() != "trip reason":
                        # Need to rewrite the file with the new header if it's missing or incorrect
                        # This is a simple approach; for large files, a backup and rewrite is safer
                        file.seek(0)
                        rows = list(reader) # Read existing data
                        file.truncate(0) # Clear the file
                        writer = csv.writer(file)
                        writer.writerow(["Date", "Location", "Miles", "Trip Reason"])
                        for row in rows:
                            if len(row) == 3: # Old format, add empty reason
                                writer.writerow(row + [""])
                            elif len(row) >= 4: # Potentially already has it or more
                                writer.writerow(row[:4]) # Take first 4
                            else: # Corrupted row, skip or handle
                                writer.writerow(row + [""] * (4 - len(row)))


                except StopIteration: # File is empty
                    writer = csv.writer(file)
                    writer.writerow(["Date", "Location", "Miles", "Trip Reason"])
            return True

        except IOError as e:
            QMessageBox.critical(None, "File Access Error", f"Cannot access or update file headers:\n{filename}\nError: {e}")
            return False
    return True


# --- Core Data Functions ---
def add_trip_record(location: str, trip_reason: str, file_path: str) -> None:
    """Appends a trip record (including trip reason) to the specified CSV file."""
    entry = [datetime.now().strftime("%Y-%m-%d"), location, LOCATIONS[location], trip_reason]
    try:
        with open(file_path, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(entry)
    except IOError as e:
        # Error will be handled by the caller (add_predefined_trip)
        raise e
    except KeyError as e:
        # Error will be handled by the caller
        raise e


def get_custom_trip_input(parent_window: QWidget, file_path: str) -> Tuple[bool, Optional[str]]:
    """Gets custom trip details (including trip reason) and adds the record."""
    location_name, ok1 = QInputDialog.getText(parent_window, "Custom Trip Input", "Enter Location Name:")
    if ok1 and location_name:
        number_str, ok2 = QInputDialog.getText(parent_window, "Custom Trip Input", f"Enter Miles for '{location_name}':")
        if ok2 and number_str:
            trip_reason, ok3 = QInputDialog.getText(parent_window, "Custom Trip Input", "Enter Trip Reason:")
            if ok3: # Allow empty trip reason if dialog is confirmed
                entry = [datetime.now().strftime("%Y-%m-%d"), location_name, number_str, trip_reason]
                try:
                    with open(file_path, 'a', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow(entry)
                    return True, f"{location_name} ({number_str} mi) - Reason: {trip_reason if trip_reason else 'N/A'}"
                except IOError as e:
                    QMessageBox.warning(parent_window, "File Error", f"Could not write trip to {os.path.basename(file_path)}:\n{e}")
                    return False, None
            # else: User cancelled trip reason input
        elif ok2:
             QMessageBox.information(parent_window, "Input Required", "Custom trip number cannot be empty.")
    elif ok1:
         QMessageBox.information(parent_window, "Input Required", "Location name cannot be empty.")
    return False, None


# --- Main Window Class ---
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.tray_manager: Optional['TrayManager'] = None
        self.data_file_path: Optional[str] = None

        self.setWindowTitle("Trip Logger")
        self.resize(QSize(300, 350)) # Increased height slightly for more buttons

        self.button_group = QButtonGroup(self)
        layout = QVBoxLayout()
        self.trip_buttons: List[QPushButton] = []

        # Updated button configuration
        location_buttons_config = {
             '505': '505',
             'Baker': 'Baker',
             'Edwards': 'Edwards',
             'HR': 'HR',
             'Buckeye': 'Buckeye'
        }
        for data_location, button_label in location_buttons_config.items():
            button = QPushButton(button_label)
            self.button_group.addButton(button)
            # Use a lambda to capture the correct location for each button
            button.clicked.connect(lambda checked=False, loc=data_location: self.add_predefined_trip(loc))
            layout.addWidget(button)
            self.trip_buttons.append(button)

        custom_button = QPushButton("Custom Trip")
        self.button_group.addButton(custom_button)
        custom_button.clicked.connect(self.add_custom_trip)
        layout.addWidget(custom_button)
        self.trip_buttons.append(custom_button) # Also disable/enable custom button

        main_container = QWidget()
        main_container.setLayout(layout)
        self.setCentralWidget(main_container)

        self._create_menus()
        self.load_settings_and_update_state()

    def set_tray_manager(self, manager: 'TrayManager') -> None:
        self.tray_manager = manager

    def _create_menus(self) -> None:
        self.set_file_action = QAction("&Set Data File...", self)
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
        loaded_path = load_data_file_path()
        is_path_valid = False
        if loaded_path:
            # Ensure the directory of the loaded path exists before calling initialize_csv
            dir_name = os.path.dirname(loaded_path)
            if not dir_name or os.path.exists(dir_name): # If dir_name is empty (just filename), it's fine
                if initialize_csv(loaded_path): # initialize_csv now also checks header
                    self.data_file_path = loaded_path
                    is_path_valid = True
                else:
                    # Path exists but init failed (permissions, header update issue)
                    self.data_file_path = None
                    save_data_file_path(None) # Clear invalid setting
                    # Error message was shown by initialize_csv
            else:
                # Directory for the saved path doesn't exist anymore
                self.data_file_path = None
                save_data_file_path(None)
                QMessageBox.warning(self, "Invalid Path", f"The directory for the saved data path no longer exists:\n{loaded_path}\nPlease set a new data file location.")
        else:
             self.data_file_path = None

        self.update_button_states(enable=is_path_valid)
        if not is_path_valid and not self.data_file_path: # Only prompt if truly no path
             self.prompt_for_initial_data_file()


    def prompt_for_initial_data_file(self):
         reply = QMessageBox.information(
              self, "Setup Required",
              "Welcome to Trip Logger!\n\nPlease select a location to save your trip data (e.g., trips.csv).",
              QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
              )
         if reply == QMessageBox.StandardButton.Ok:
              self.prompt_and_set_data_file()

    def prompt_and_set_data_file(self) -> bool:
        documents_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        current_dir = os.path.dirname(self.data_file_path) if self.data_file_path else documents_path
        default_name = os.path.basename(self.data_file_path) if self.data_file_path else "trips.csv"
        suggested_path = os.path.join(current_dir, default_name)

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Select or Create Data File", suggested_path, "CSV Files (*.csv);;All Files (*)"
        )

        if file_path:
            if not file_path.lower().endswith(".csv"):
                file_path += ".csv"
            if initialize_csv(file_path):
                self.data_file_path = file_path
                save_data_file_path(self.data_file_path)
                self.update_button_states(enable=True)
                self.statusBar().showMessage(f"Data file set to: {self.data_file_path}", 5000)
                return True
            else:
                self.data_file_path = None # Reset on failure
                save_data_file_path(None)
                self.update_button_states(enable=False)
                # Error message already shown by initialize_csv
                return False
        return False

    def update_button_states(self, enable: bool) -> None:
        for button in self.trip_buttons: # self.trip_buttons includes all predefined and custom
             button.setEnabled(enable)
        if not enable:
             self.statusBar().showMessage("No valid data file set. Use File -> Set Data File...", 0)
        else:
            if self.data_file_path: # Clear status bar if path is set and buttons enabled
                self.statusBar().clearMessage()


    def _is_path_valid(self) -> bool:
         if not self.data_file_path:
              QMessageBox.warning(self, "Setup Required", "Please set the data file location first (File menu).")
              return False
         # Re-check writability and header (initialize_csv does this)
         if not initialize_csv(self.data_file_path):
             self.update_button_states(False)
             return False
         return True

    def add_predefined_trip(self, location: str) -> None:
        """Handles adding a predefined trip, including prompting for trip reason."""
        if not self._is_path_valid():
            return

        # Prompt for Trip Reason
        trip_reason, ok = QInputDialog.getText(self, "Trip Reason", f"Enter reason for trip to {location}:")

        if ok: # User clicked OK, reason can be empty
            try:
                add_trip_record(location, trip_reason, self.data_file_path)
                if self.tray_manager:
                    mileage = LOCATIONS[location]
                    reason_display = f" - Reason: {trip_reason}" if trip_reason else ""
                    self.tray_manager.show_notification(f"Added: {location} ({mileage} mi){reason_display}")
            except IOError as e:
                QMessageBox.warning(self, "File Error", f"Could not write trip:\n{e}")
                self.update_button_states(False) # Disable buttons if path is unwritable
            except KeyError:
                 QMessageBox.critical(self, "Configuration Error", f"Internal error: Location '{location}' not found in LOCATIONS.")
            except Exception as e:
                QMessageBox.critical(self, "Unexpected Error", f"An unexpected error occurred:\n{e}")
        # else: User cancelled the trip reason input, so do nothing.

    def add_custom_trip(self) -> None:
        if not self._is_path_valid():
            return
        success, details = get_custom_trip_input(self, self.data_file_path)
        if success and self.tray_manager and details: # details can be None
             self.tray_manager.show_notification(f"Added custom trip: {details}")


    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
        if self.tray_manager:
             self.tray_manager.tray.showMessage("Still Running",
                 "Trip Logger is running in the system tray.",
                 QSystemTrayIcon.MessageIcon.Information, 1500)

    def get_set_file_action(self) -> QAction:
         return self.set_file_action

# --- System Tray Class ---
class TrayManager(QObject):
    def __init__(self, application: QApplication, main_window: MainWindow, app_icon: QIcon, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.app = application
        self.main_window = main_window
        self.icon = app_icon

        self.tray = QSystemTrayIcon(self.icon, parent=self) # Pass self as parent
        self.tray.setToolTip(APPLICATION_NAME)

        self.menu = QMenu()
        show_action = QAction("Show Logger Window", self)
        show_action.triggered.connect(self.main_window.show)
        show_action.triggered.connect(self.main_window.activateWindow) # Ensure it gets focus
        self.menu.addAction(show_action)

        self.menu.addAction(self.main_window.get_set_file_action())
        self.menu.addSeparator()
        quit_action = QAction("Quit Trip Logger", self)
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.setVisible(True) # Make sure it's visible
        self.tray.activated.connect(self.on_tray_icon_activated)

    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger: # Typically left click
            self.main_window.show()
            self.main_window.activateWindow() # Bring to front and give focus

    def show_notification(self, message: str) -> None:
        self.tray.showMessage(
            "Trip Added", message, # Changed title slightly
            QSystemTrayIcon.MessageIcon.Information, NOTIFICATION_DURATION_MS
        )

# --- Main Execution Block ---
if __name__ == "__main__":
    shared_memory = QSharedMemory(SHARED_MEM_KEY)
    if shared_memory.attach(QSharedMemory.AccessMode.ReadOnly):
        # QMessageBox.information(None, "Application Running", "Another instance of TripLogger is already running.")
        # Instead of a message box, just exit silently for a cleaner user experience.
        # If you need to signal the existing instance to show its window,
        # that would require more complex inter-process communication (e.g., QLocalServer/Socket).
        print("Another instance is already running. Exiting.")
        sys.exit(0)

    if not shared_memory.create(1):
        error_message = f"Could not create shared memory segment: {shared_memory.errorString()}"
        # Attempt to create a temp app for the message box if QApplication doesn't exist yet
        _temp_app_instance = QApplication.instance()
        if not _temp_app_instance:
            _temp_app_instance = QApplication(sys.argv) # Create a temporary one
        
        QMessageBox.critical(None, "Application Startup Error", error_message)
        if shared_memory.isAttached(): # Should not be necessary if create failed, but good practice
            shared_memory.detach()
        sys.exit(1)
    
    # Make sure to detach shared memory when the application quits
    # This is crucial for allowing the next run to acquire the lock
    def cleanup_shared_memory():
        if shared_memory.isAttached():
            shared_memory.detach()
        print("Shared memory detached.")

    QApplication.setOrganizationName(ORGANIZATION_NAME)
    QApplication.setApplicationName(APPLICATION_NAME)

    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_shared_memory) # Connect cleanup
    app.setQuitOnLastWindowClosed(False) # Important for tray icon behavior

    # --- Load Icon ---
    # Use a proper check for the icon path
    if os.path.exists(ICON_PATH) and ICON_PATH != QIcon.fromTheme("application-x-executable").name():
        app_icon = QIcon(ICON_PATH)
    else:
        print(f"Warning: Icon file '{ICON_FILENAME}' not found at '{ICON_PATH}'. Using default system icon.")
        app_icon = QIcon.fromTheme("application-x-executable", QIcon()) # Provide a fallback QIcon()
    app.setWindowIcon(app_icon) # Set for the whole application


    window = MainWindow()
    # Pass the app_icon also to TrayManager if it uses it
    tray_manager = TrayManager(app, window, app_icon) # Pass actual app_icon
    window.set_tray_manager(tray_manager)

    window.show()
    sys.exit(app.exec())
