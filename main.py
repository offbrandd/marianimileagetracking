import csv
from datetime import datetime
from PySide6.QtWidgets import QApplication, QWidget, QMainWindow, QPushButton, QButtonGroup, QVBoxLayout, QDialog, QDialogButtonBox, QLabel, QInputDialog, QLineEdit
from PySide6.QtCore import QSize, Qt, QDir
import sys
from functools import partial


locations = {
    '505': '5',
    'Baker/Edwards': '1',
    'Buckeye': '7'
}

filename = 'trips.csv'

#TODO: custom entries

def add_trip(location):
    entry = [datetime.now().strftime("%Y-%m-%d"), location,locations[location]]    
    with open(filename, 'a', newline='') as file:
        write = csv.writer(file)
        write.writerow(entry)
        file.close()

def get_custom_trip(parent_window):
    """
    Shows a dialog to get custom trip details and adds it to the CSV.
    """
    # QInputDialog.getText returns a tuple: (text, ok_boolean)
    # parent_window (self): Ensures the dialog is modal to the main window
    # "Custom Trip Input": The title of the dialog window
    # "Enter Location Name:": The label text shown above the input field
    text, ok = QInputDialog.getText(parent_window,
                                      "Custom Trip Input",
                                      "Enter Location Name:")

    # Check if the user clicked OK and entered some text
    if ok and text:
        print(f"User entered: {text}")
        # You might want a second dialog for the 'number' or have a default/logic
        # For simplicity, let's ask for the number too
        num_text, num_ok = QInputDialog.getText(parent_window,
                                                "Custom Trip Input",
                                                f"Enter Number for '{text}':")

        if num_ok and num_text:
             # Add the custom entry to the CSV
            entry = [datetime.now().strftime("%Y-%m-%d"), text, num_text]
            with open(filename, 'a', newline='') as file:
                write = csv.writer(file)
                write.writerow(entry)
            print(f"Added custom trip: {text} ({num_text})")
        elif num_ok:
             print("Custom trip number cannot be empty. Cancelled.")
        else:
            print("Custom trip number input cancelled.")

    elif ok:
        print("Location name cannot be empty. Cancelled.")
    else:
        print("Custom trip input cancelled.")


# Subclass QMainWindow to customize your application's main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Trip Logger")
        self.setFixedSize(QSize(400, 300))

        group = QButtonGroup()

        button505 = QPushButton("505")
        group.addButton(button505)
        button505.clicked.connect(partial(add_trip, "505"))

        buttonBaker = QPushButton("Baker/Edwards/HR")
        group.addButton(buttonBaker)
        buttonBaker.clicked.connect(partial(add_trip, "Baker/Edwards"))

        buttonBuckeye = QPushButton("Buckeye")
        group.addButton(buttonBuckeye)
        buttonBuckeye.clicked.connect(partial(add_trip, "Buckeye"))

        buttonCustom = QPushButton("Custom")
        group.addButton(buttonCustom)
        buttonCustom.clicked.connect(partial(get_custom_trip, self))


        layout = QVBoxLayout()
        for button in group.buttons():
            layout.addWidget(button)

        main_container = QWidget()
        main_container.setLayout(layout)
        self.setCentralWidget(main_container)


app = QApplication(sys.argv)

# Create a Qt widget, which will be our window.
window = MainWindow()
window.show() # Windows are hidden by default

#start the event loop
app.exec()