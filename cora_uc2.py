'''
 # @ Author: Jie Yang
 # @ Create Time: 2024.6
 # @ Last Modified by: Jie Yang  Contact: jieynlp@gmail.com
 '''
# -*- coding: utf-8 -*-

import sys
import csv
import pickle
import xml.etree.ElementTree as ET
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextEdit, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QInputDialog,
                             QListWidget, QComboBox, QDateEdit, QRadioButton, QButtonGroup, QGridLayout, QCheckBox)
from PyQt5.QtCore import Qt, QDateTime, QTime,  QDate, QTimer
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument
from PyQt5.QtCore import QRegularExpression
## enable adjust column width of annotation panel
class EditableHeaderView(QHeaderView):
    def __init__(self, orientation, parent, annotation_tool=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.sectionDoubleClicked.connect(self.edit_header)
        self.annotation_tool = annotation_tool
        

    def edit_header(self, logicalIndex):
        if logicalIndex < 7:  # Prevent editing the first 7 columns
            return
        
        currentName = self.model().headerData(logicalIndex, self.orientation(), Qt.DisplayRole)
        newName, ok = QInputDialog.getText(self, "Edit Column Name", "Enter new name:", text=currentName)
        if ok and newName:
            self.model().setHeaderData(logicalIndex, self.orientation(), newName, Qt.DisplayRole)
        
        # Update the headers in AnnotationTool
        if self.annotation_tool != None:
            updated_columns = [self.model().headerData(i, Qt.Horizontal, Qt.DisplayRole) for i in range(self.model().columnCount())]
            if self.annotation_tool.patient_level_radio.isChecked():
                self.annotation_tool.patient_headers = updated_columns
            else:
                self.annotation_tool.record_headers = updated_columns
            
            print("Updated headers:", updated_columns)

class AnnotationTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_row = None
        self.csv_file_path = None
        self.column_names = []
        self.title_list = []
        self.records = []
        self.filtered_records = []
        self.is_switching_levels = False ## if switching annotation level, patient vs record
        self._is_updating = False  # if the annotation table is updating
        self.custom_column_count = 0  # To keep track of added columns
        self.patient_annotations = {}  # To store patient-level annotations
        self.record_annotations = {}   # To store record-level annotations
        self.patient_headers = ['Patient ID', 'Record Count', 'Start Date', 'End Date', 'Annotation Start', 'Annotation End', 'Time Cost', 'Self-harm','RecordID','Comment', '+']
        self.record_headers = ['PatientID', 'RecordID', 'Record_Date', 'Record_Type', 'Annotation Start', 'Annotation End', 'Time Cost', 'Self-harm', 'Comment', '+']
        self.load_keywords = {}
        self.extend_keywords = []
        self.annotation_start_times = {}
        self.initUI()
        
        # Create status bar
        self.statusBar = self.statusBar()
        self.patient_count_label = QLabel()
        self.record_count_label = QLabel()
        self.current_time_label = QLabel()
        self.total_time_cost_label = QLabel()
        self.current_case_time_label = QLabel()

        self.statusBar.addPermanentWidget(self.patient_count_label)
        self.statusBar.addPermanentWidget(self.record_count_label)
        self.statusBar.addPermanentWidget(self.current_time_label)
        self.statusBar.addPermanentWidget(self.total_time_cost_label)
        self.statusBar.addPermanentWidget(self.current_case_time_label)

        # Start timer for updating status bar
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status_bar)
        self.timer.start(1000)  # Update every second

        # Initialize total time cost and current case time
        self.total_time_cost = 0
        self.current_case_start_time = QDateTime.currentDateTime()

    def initUI(self):
        self.setWindowTitle('CORA-UC2')
        self.setGeometry(100, 100, 1600, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left panel: Record list and controls
        left_panel = QVBoxLayout()
        main_layout.addLayout(left_panel, 1)
        
        load_level_layout = QHBoxLayout()
        ## add file load button
        self.load_button = QPushButton("Load XML File")
        self.load_button.clicked.connect(self.load_file)
        load_level_layout.addWidget(self.load_button)
        # ##  TODO: load project
        # self.load_project_button = QPushButton("Load Project")
        # self.load_project_button.clicked.connect(self.load_project)
        # load_level_layout.addWidget(self.load_project_button)
        
        left_panel.addLayout(load_level_layout)
        # Add radio buttons for annotation level, patient level or record level
        annotation_level_layout = QHBoxLayout()
        self.annotation_level_label = QLabel("Annotation Level:")
        self.patient_level_radio = QRadioButton("Patient")
        self.record_level_radio = QRadioButton("Record")
        self.patient_level_radio.setChecked(True)  # Default to patient level
        # Create a button group
        self.annotation_level_group = QButtonGroup(self)
        self.annotation_level_group.addButton(self.patient_level_radio)
        self.annotation_level_group.addButton(self.record_level_radio)
        
        self.annotation_level_group.buttonClicked.connect(self.on_annotation_level_changed)
        annotation_level_layout.addWidget(self.annotation_level_label)
        annotation_level_layout.addWidget(self.patient_level_radio)
        annotation_level_layout.addWidget(self.record_level_radio)
        left_panel.addLayout(annotation_level_layout)

        ## disable the auto calling of combo update function, which include update_display. This will make the code slow
        
        # Add droplists for PatientID and RecordID
        filter_layout = QHBoxLayout()
        self.patient_id_label = QLabel("Patient ID:")
        self.patient_id_combo = QComboBox()
        self.patient_id_combo.addItem("All")
        self.record_id_label = QLabel("Record ID:")
        self.record_id_combo = QComboBox()
        self.record_id_combo.addItem("All")
               
        filter_layout.addWidget(self.patient_id_label)
        filter_layout.addWidget(self.patient_id_combo)
        filter_layout.addWidget(self.record_id_label)
        filter_layout.addWidget(self.record_id_combo)
        left_panel.addLayout(filter_layout)
        
        additional_filter_layout = QHBoxLayout()
        self.record_type_label = QLabel("Record Type:")
        self.record_type_combo = QComboBox() 
        self.record_type_combo.addItem("All")
        additional_filter_layout.addWidget(self.record_type_label)
        additional_filter_layout.addWidget(self.record_type_combo)
        
        # Add Power Highlight checkbox
        self.power_highlight_checkbox = QCheckBox("Power Highlight")
        self.power_highlight_checkbox.setChecked(False)  # Set to unchecked by default
        self.power_highlight_checkbox.stateChanged.connect(self.highlight_keywords)
        additional_filter_layout.addWidget(self.power_highlight_checkbox)
        
        left_panel.addLayout(additional_filter_layout)
        
        # Connect droplist selection change events
        self.patient_id_combo.currentTextChanged.connect(self.on_patient_id_changed)
        self.record_id_combo.currentTextChanged.connect(self.update_display)
        self.record_type_combo.currentTextChanged.connect(self.on_record_type_changed)
        
        # Keyword highlighting
        keyword_layout = QVBoxLayout()
        # Highlight First row: Label and Button
        top_row_layout = QHBoxLayout()
        self.keyword_label = QLabel("Keywords (comma-separated):")
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.load_keyword_file)
        top_row_layout.addWidget(self.keyword_label)
        top_row_layout.addStretch(1)  # This adds flexible space between the label and button
        top_row_layout.addWidget(self.browse_button)
        keyword_layout.addLayout(top_row_layout)

        # Highlight Second row: Entry field
        self.keyword_entry = QLineEdit()
        keyword_layout.addWidget(self.keyword_entry)
        self.keyword_entry.returnPressed.connect(self.highlight_keywords)
        left_panel.addLayout(keyword_layout)
        
        # Highlight third row, keyword table
            # Annotation table
        self.keyword_table = QTableWidget()
        self.keyword_table.setColumnCount(2)
        
        # Create and set the custom header
        custom_header = EditableHeaderView(Qt.Horizontal, self.keyword_table)
        self.keyword_table.setHorizontalHeader(custom_header)
        
        self.keyword_table.setHorizontalHeaderLabels(['Keyword', 'Label'])
        self.keyword_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        left_panel.addWidget(self.keyword_table)        
        
        ## add file save button
        save_level_layout = QHBoxLayout()
        self.export_button = QPushButton("Export Annotation")
        self.export_button.clicked.connect(self.save_annotation_to_file)
        save_level_layout.addWidget(self.export_button)
        ## TODO: save project
        # self.save_project_button = QPushButton("Save Project")
        # self.save_project_button.clicked.connect(self.save_project)
        # save_level_layout.addWidget(self.save_project_button)
        left_panel.addLayout(save_level_layout)
        # # Annotation controls
        # annotation_controls = QHBoxLayout()
        # self.start_annotation_button = QPushButton("Start Annotation")
        # self.end_annotation_button = QPushButton("End Annotation")
        # self.end_annotation_button.setEnabled(False)
        # self.start_annotation_button.clicked.connect(self.start_annotation)
        # self.end_annotation_button.clicked.connect(self.end_annotation)
        # annotation_controls.addWidget(self.start_annotation_button)
        # annotation_controls.addWidget(self.end_annotation_button)
        # left_panel.addLayout(annotation_controls)
        
        # # Add Column button, disabled due to same function implemented on clicking column +
        # self.add_column_button = QPushButton("Add Column")
        # self.add_column_button.clicked.connect(self.add_new_column)
        # left_panel.addWidget(self.add_column_button)


        ## Right panel: Text display and annotation
        right_panel = QVBoxLayout()

        # Text display area
        self.text_display = AnnotationTextEdit(self)
        
        ## set text display module non-editable, but can be selected and highlighted
        self.text_display.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        right_panel.addWidget(self.text_display, 3)


        # Annotation table
        self.annotation_table = QTableWidget()
        self.annotation_table.setColumnCount(7)
        
        # Create and set the custom header
        custom_header = EditableHeaderView(Qt.Horizontal, self.annotation_table, self)
        self.annotation_table.setHorizontalHeader(custom_header)
        
        self.annotation_table.setHorizontalHeaderLabels(self.patient_headers)  ## default in patient headers
        self.annotation_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        right_panel.addWidget(self.annotation_table)
        # Connect the header click event add new column
        self.annotation_table.horizontalHeader().sectionClicked.connect(self.onHeaderClicked)
        self.annotation_table.cellChanged.connect(self.on_cell_changed)

        ### TODO: filtering notes with date, patient/record droplist need to be updated based on the availability of records.
        # ## date filtering
        # date_layout = QHBoxLayout()
        # # Start date
        # start_label = QLabel("Start Date:")
        # self.start_date = QDateEdit()
        # self.start_date.setCalendarPopup(True)
        # self.start_date.setDate(QDate.currentDate().addDays(-30))  # Default to 30 days ago
        # self.start_date.dateChanged.connect(self.on_date_changed)
        
        # # End date
        # end_label = QLabel("End Date:")
        # self.end_date = QDateEdit()
        # self.end_date.setCalendarPopup(True)
        # self.end_date.setDate(QDate.currentDate())  # Default to today
        # self.end_date.dateChanged.connect(self.on_date_changed)
        
        # # Add widgets to date layout
        # date_layout.addWidget(start_label)
        # date_layout.addWidget(self.start_date)
        # date_layout.addWidget(end_label)
        # date_layout.addWidget(self.end_date)
        # date_layout.addWidget(self.filter_button)
        # left_panel.insertLayout(1, date_layout)
        
        main_layout.addLayout(right_panel, 5)
        main_layout.setStretch(0, 1)  # Left panel
        main_layout.setStretch(1, 5)  # Right panel

    def load_file(self):
        print("load_file.")
        self.is_switching_levels = True ## assume first load file as switch level to disable annotation saving
        file_path, _ = QFileDialog.getOpenFileName(self, "Open XML File", "", "XML Files (*.xml)")
        if file_path:
            self.records = self.parse_xml(file_path)
            self.filtered_records = self.records.copy()
            self.update_droplists()
            self.update_display()
            # Set CSV file path
            if self.patient_level_radio.isChecked():
                self.csv_file_path = file_path.rsplit('.', 1)[0] + '_patient_annotations.csv'
            else:
                self.csv_file_path = file_path.rsplit('.', 1)[0] + '_note_annotations.csv'
            # Reset total time cost and current case time
            self.total_time_cost = 0
            self.current_case_start_time = QDateTime.currentDateTime()
        self.is_switching_levels = False
        
    def parse_xml(self, file_path):
        print("parse_xml for file: ", file_path)
        tree = ET.parse(file_path)
        root = tree.getroot()
        records = []
        for row in root.findall('ROW'):
            record = {}
            for column in row.findall('COLUMN'):
                name = column.get('NAME')
                if name not in self.column_names:
                    self.column_names.append(name)
                value = column.text.strip() if column.text else ""
                record[name] = value
            records.append(record)
        return records

    def update_droplists(self):
        print("update_droplists.")
        patient_ids = set(record['PatientID'] for record in self.records)
        record_ids = set(record['RecordID'] for record in self.records)
        record_types = set(record['Record_Type'] for record in self.records)
        # print(record_types)
        
        self.patient_id_combo.clear()
        self.record_id_combo.clear()
        self.record_type_combo.clear()
        
        self.patient_id_combo.blockSignals(True)
        self.record_id_combo.blockSignals(True)
        self.record_type_combo.blockSignals(True)
        
        self.patient_id_combo.addItem("All")
        self.patient_id_combo.addItems(sorted(patient_ids))
        
        self.record_id_combo.addItem("All")
        self.record_id_combo.addItems(sorted(record_ids))

        self.record_type_combo.addItem("All")
        self.record_type_combo.addItems(sorted(record_types))
        
        self.patient_id_combo.blockSignals(False)
        self.record_id_combo.blockSignals(False)
        self.record_type_combo.blockSignals(False)

        # self.update_record_id_droplist_with_patient("All")


    def update_record_id_droplist_with_patient(self, selected_patient):
        print("update_record_id_droplist_with_patient.")
        self.record_id_combo.blockSignals(True)
        self.record_id_combo.clear()
        if selected_patient == "All":
            
            self.record_id_combo.addItem("All")
            
            record_ids = set(record['RecordID'] for record in self.records)
        else:
            record_ids = set(record['RecordID'] for record in self.records if record['PatientID'] == selected_patient)
        print("update record id:", record_ids)
        print("select patient id:", selected_patient)
        ## TODO: sort records with date
        self.record_id_combo.addItems(["All"] +sorted(record_ids))
        self.record_id_combo.blockSignals(False)
        

    def update_record_id_droplist_with_record_type(self, selected_type):
        print("update_record_id_droplist_with_record_type.")
        self.record_id_combo.blockSignals(True)
        self.record_id_combo.clear()
        if selected_type == "All":
            self.record_id_combo.addItem("All")
            self.record_id_combo.blockSignals(False)
            record_ids = set(record['RecordID'] for record in self.records)
        else:
            record_ids = set(record['RecordID'] for record in self.records if record['Record_Type'] == selected_type)
        print("update record id:", record_ids)
        print("select record type:", selected_type)
        ## TODO: sort records with date
        self.record_id_combo.addItems(["All"] +sorted(record_ids))
        self.record_id_combo.blockSignals(False)

    def on_patient_id_changed(self, selected_patient):
        print("on_patient_id_changed. selected patient:", selected_patient)
        self.update_record_id_droplist_with_patient(selected_patient)
        self.update_display()
        
    def on_record_type_changed(self, selected_record_type):
        print("on_record_type_changed. selected record type: ", selected_record_type)
        self.update_record_id_droplist_with_record_type(selected_record_type)
        self.update_display()


    def update_display(self):
        print("update_display.")
        selected_patient = self.patient_id_combo.currentText()
        selected_record_type = self.record_type_combo.currentText()
        selected_record = self.record_id_combo.currentText()
        # Reset current case start time
        self.current_case_start_time = QDateTime.currentDateTime()
        
        self.filtered_records = self.records.copy()
        if selected_patient != "All":
            self.filtered_records = [record for record in self.filtered_records if record['PatientID'] == selected_patient]
        
        if selected_record_type != "All":
            self.filtered_records = [record for record in self.filtered_records if record['Record_Type'] == selected_record_type]
        
        if selected_record != "All":
            self.filtered_records = [record for record in self.filtered_records if record['RecordID'] == selected_record]
        
        ## update display text
        self.text_display.setPlainText("\n".join([self.display_format(a)[0] for a in self.filtered_records]))
        ## record title text for highlight
        self.title_list = [self.display_format(a)[1] for a in self.filtered_records]
        
        ## highlight
        full_highlight = True 
        if selected_patient == "All":
            full_highlight = False
        self.highlight_keywords(full_highlight)
        # self.highlight_title()
        
        # Update annotation table based on the selected annotation level
        self.is_switching_levels = True
        if self.patient_level_radio.isChecked():
            self.update_annotation_table_for_patient_level()
        else:
            self.update_annotation_table_for_record_level()
        self.is_switching_levels = False
        
        # Record start time for the current patient/record
        current_id = self.get_current_id()
        if current_id not in self.annotation_start_times:
            self.annotation_start_times[current_id] = QDateTime.currentDateTime()
        
        # Reset current case start time
        self.current_case_start_time = QDateTime.currentDateTime()

    def get_current_id(self):
        if self.patient_level_radio.isChecked():
            return self.patient_id_combo.currentText()
        else:
            return self.record_id_combo.currentText()

    def display_format(self, record):
        # print("display_format.")
        title_text = ""
        for name in self.column_names:
            if name != 'Record':
                title_text += name +": " + record[name] +", "
        title_text = title_text.strip(", ")
        structure_text = title_text +"\n"
        # print("display format:",structure_text)
        structure_text += "Record:\n"+record["Record"]+"\n"
        return structure_text, title_text

    def load_keyword_file(self):
        print("load_keyword_file.")
        file_path, _ = QFileDialog.getOpenFileName(self, "Open txt File", "", "TXT Files (*.txt)")
        if file_path:
            keyword_texts = open(file_path, "r").readlines()
            for each_line in keyword_texts:
                each_line = each_line.strip()
                if "|" in each_line:
                    keyword, label = each_line.rsplit("|", 1)
                    self.load_keywords[keyword.strip()] = label.strip()
                else:
                    self.load_keywords[each_line] = ""
            self.extend_existing_keywords()
            self.update_keyword_table()
            selected_patient = self.patient_id_combo.currentText()
            full_highlight = True
            if selected_patient == 'All':
                full_highlight = False
            self.highlight_keywords(full_highlight)
    
    
    def extend_existing_keywords(self):
        print("extend_existing_keywords.")
        english_stop_words = ["i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself", "they", "them", "their", "theirs", "themselves", "what", "which", "who", "whom", "this", "that", "these", "those", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", "for", "with", "about", "against", "between", "into", "through", "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now", "including", 'management', 'following', 'discharge', 'community', 'material', 'educational', 'progress', 'reported', 'reviewed', 'encounter', 'provider', 'description', 'available', 'duration', 'document', 'affected', 'frequency', 'component', 'clinical', 'specified', 'evaluation', 'protocol', 'positive', 'subsequent', 'multiple', 'unspecified', 'healthcare', 'patients', 'providers']
        for keyword, v in self.load_keywords.items():
            special_chars = "!@#$%^&*()_+-={}[]:;\"'<>,.?/~`"
            for char in special_chars:
                keyword = keyword.replace(char, ' ')
            subkeyword_list = keyword.split()
            for subkeyword in subkeyword_list:
                if subkeyword not in english_stop_words and len(subkeyword) > 7: ## keep non stop word and long word only
                    self.extend_keywords.append(subkeyword)
        self.extend_keywords = list(set(self.extend_keywords))
        print("Extend keyword num:", len(self.extend_keywords))
        
    def update_status_bar(self):
        # print("update status bar.")
        # Update patient count
        total_patients = len(set(record['PatientID'] for record in self.records))
        self.patient_count_label.setText(f"Total Patients: {total_patients}")

        # Update record count
        total_records = len(self.records)
        self.record_count_label.setText(f"Total Records: {total_records}")

        # Update current time
        current_time = QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')
        self.current_time_label.setText(f"Current Time: {current_time}")

        # Update total time cost
        self.total_time_cost += 1  # Increment by 1 second
        total_hours, total_remainder = divmod(self.total_time_cost, 3600)
        total_minutes, total_seconds = divmod(total_remainder, 60)
        total_time_cost_str = f"{total_hours:02d}:{total_minutes:02d}:{total_seconds:02d}"
        self.total_time_cost_label.setText(f"Total Annotation Time: {total_time_cost_str}")

        # Update current case waiting time
        current_case_time = self.current_case_start_time.secsTo(QDateTime.currentDateTime())
        case_hours, case_remainder = divmod(current_case_time, 3600)
        case_minutes, case_seconds = divmod(case_remainder, 60)
        case_time_str = f"{case_hours:02d}:{case_minutes:02d}:{case_seconds:02d}"
        self.current_case_time_label.setText(f"Current Case Time: {case_time_str}")

    def highlight_keywords(self, full_highlight=True):
        print("Highlight keywords, highlight all:", full_highlight)
        keywords = [keyword for keyword in self.keyword_entry.text().split(',') if keyword.strip()]
        keywords += self.load_keywords.keys()
        keywords = [keyword.strip().lower() for keyword in keywords]
        if self.power_highlight_checkbox.isChecked(): ## power highlight model
            keywords += self.extend_keywords 
        # Clear previous highlights
        cursor = self.text_display.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setCharFormat(QTextCharFormat())
        cursor.clearSelection()
        print("a")
        # Define highlight format
        highlight_format = QTextCharFormat()
        highlight_format.setForeground(QColor(Qt.red))
        print("a")
        # Get the entire document text and convert to lowercase for searching
        document = self.text_display.document()
        text = document.toPlainText().lower()
        if full_highlight != False or type(full_highlight) != type(False):
            # text_length = len(text)
            # text = text[:min(text_length, 10000)]
            cursor = QTextCursor(document)
            # Highlight keywords
            print("a")
            for keyword in set(keywords):
                start_index = 0
                while True:
                    index = text.find(keyword, start_index)
                    if index == -1:
                        break
                    # Select and highlight the original text (preserving case)
                    
                    cursor.setPosition(index)
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(keyword))
                    cursor.mergeCharFormat(highlight_format)
                    start_index = index + len(keyword)
            print("Highlight keywords complete.")
        self.highlight_title(full_highlight)
        

    def highlight_title(self,full_highlight ):
        print("highlight_title,  highlight all: ", full_highlight)

        # Define highlight format
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor(Qt.yellow))

        # Get the entire document text
        document = self.text_display.document()
        text = document.toPlainText()

        # Split the text into lines
        lines = text.split('\n')
        cursor = QTextCursor(document)
        # Highlight lines that start with "PatientID: "
        for line_number, line in enumerate(lines):
            if full_highlight != False or type(full_highlight) != type(False):
                # if line_number > 300:
                #     break
                if line.startswith("PatientID: "):
                    print(f"Highlighting title line {line_number}: {line},  highlight all: {full_highlight}")

                    # Calculate the position of the start of the line in the entire text
                    start_index = text.find(line)

                    # Select and highlight the entire line
                    
                    cursor.setPosition(start_index)
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(line))
                    cursor.mergeCharFormat(highlight_format)
        
        print("highlighting title complete.")

    # def highlight_title(self):
    #     print("run highlight for 'PatientID: '")

    #     # Define highlight format
    #     highlight_format = QTextCharFormat()
    #     highlight_format.setBackground(QColor(Qt.yellow))

    #     # Get the entire document text
    #     document = self.text_display.document()
    #     text = document.toPlainText()

    #     # Keyword to search
    #     keyword = "PatientID: "

    #     # Start searching for the keyword in the document text
    #     start_index = 0
    #     while True:
    #         # Find the index of the next occurrence of "PatientID: "
    #         index = text.find(keyword, start_index)

    #         # If no more occurrences are found, exit the loop
    #         if index == -1:
    #             break

    #         # Select and highlight the entire line starting with "PatientID: "
    #         cursor = QTextCursor(document)
    #         cursor.setPosition(index)
            
    #         # Move cursor to the end of the line (until the next newline character or end of text)
    #         end_of_line = text.find('\n', index)
    #         if end_of_line == -1:
    #             end_of_line = len(text)  # If no newline, highlight till the end of the text
            
    #         # Move and highlight the entire line
    #         cursor.setPosition(index)
    #         cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, end_of_line - index)
    #         cursor.mergeCharFormat(highlight_format)

    #         # Move to the next occurrence
    #         start_index = end_of_line + 1

    #     print("highlighting complete")

    # def highlight_title(self):
    #     print("run highlight title")
    #     ## direct match, no case conversion
    #     # Define highlight format
    #     highlight_format = QTextCharFormat()
    #     highlight_format.setBackground(QColor(Qt.yellow))

    #     # Get the entire document text and convert to lowercase for searching
    #     document = self.text_display.document()
    #     text = document.toPlainText()

    #     # Highlight keywords
    #     print("title list:", self.title_list)
    #     for keyword in self.title_list:
    #         print("title highlight, ", keyword)
    #         start_index = 0
    #         while True:
    #             index = text.find(keyword, start_index)
    #             if index == -1:
    #                 break
                
    #             # Select and highlight the original text (preserving case)
    #             cursor = QTextCursor(document)
    #             cursor.setPosition(index)
    #             cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(keyword))
    #             cursor.mergeCharFormat(highlight_format)
                
    #             start_index = index + len(keyword)
                
    ## event for annotation change
    def on_annotation_level_changed(self):
        print("Annotation level changing")  # Debug print
        self.is_switching_levels = True ## add a flag to disable the cell changing result saving, as this will same intermediate results and loss annotation results.
        is_patient_level = self.patient_level_radio.isChecked()
        self.set_annotation_table_headers(is_patient_level)
        if is_patient_level:
            self.update_annotation_table_for_patient_level()
        else:
            self.update_annotation_table_for_record_level()
        self.is_switching_levels = False
    
    def set_annotation_table_headers(self, is_patient_level):
        headers = self.patient_headers if is_patient_level else self.record_headers
        self.annotation_table.setColumnCount(len(headers))
        for i, header in enumerate(headers):
            self.annotation_table.setHorizontalHeaderItem(i, QTableWidgetItem(header))
    
    def update_annotation_table_for_patient_level(self):
        self.set_annotation_table_headers(True)
        self.annotation_table.setRowCount(0)
        patient_data = {}

        for record in self.filtered_records:
            patient_id = record['PatientID']
            if patient_id not in patient_data:
                patient_data[patient_id] = {
                    'record_count': 0,
                    'start_date': record['Record_Date'],
                    'end_date': record['Record_Date']
                }
            else:
                patient_data[patient_id]['record_count'] += 1
                patient_data[patient_id]['start_date'] = min(patient_data[patient_id]['start_date'], record['Record_Date'])
                patient_data[patient_id]['end_date'] = max(patient_data[patient_id]['end_date'], record['Record_Date'])

        for i, (patient_id, data) in enumerate(sorted(patient_data.items())):
            self.annotation_table.insertRow(i)
            self.annotation_table.setItem(i, 0, QTableWidgetItem(patient_id))
            self.annotation_table.setItem(i, 1, QTableWidgetItem(str(data['record_count'] + 1)))
            self.annotation_table.setItem(i, 2, QTableWidgetItem(data['start_date']))
            self.annotation_table.setItem(i, 3, QTableWidgetItem(data['end_date']))
            
            # Retrieve stored annotation data
            annotation_data = self.patient_annotations.get(patient_id, {})
            for col, header in enumerate(self.patient_headers[4:-1]):  # Start from 'Annotation Start', exclude '+'
                self.annotation_table.setItem(i, col + 4, QTableWidgetItem(annotation_data.get(header, '')))

    def update_annotation_table_for_record_level(self):
        self.set_annotation_table_headers(False)
        self.annotation_table.setRowCount(0)
        for i, record in enumerate(self.filtered_records):
            self.annotation_table.insertRow(i)
            self.annotation_table.setItem(i, 0, QTableWidgetItem(record['PatientID']))
            self.annotation_table.setItem(i, 1, QTableWidgetItem(record['RecordID']))
            self.annotation_table.setItem(i, 2, QTableWidgetItem(record['Record_Date']))
            self.annotation_table.setItem(i, 3, QTableWidgetItem(record['Record_Type']))
            
            # Retrieve stored annotation data
            annotation_data = self.record_annotations.get(record['RecordID'], {})
            for col, header in enumerate(self.record_headers[4:-1]):  # Start from 'Annotation Start', exclude '+'
                self.annotation_table.setItem(i, col + 4, QTableWidgetItem(annotation_data.get(header, '')))

    def update_keyword_table(self):
        # self.set_keyword_table_headers(False)
        self.keyword_table.setRowCount(0)
        for i, (keyword, label) in enumerate(self.load_keywords.items()):
            self.keyword_table.insertRow(i)
            self.keyword_table.setItem(i, 0, QTableWidgetItem(keyword))
            self.keyword_table.setItem(i, 1, QTableWidgetItem(label))

                
                
    ## add new column through table head
    def onHeaderClicked(self, logicalIndex):
        if logicalIndex == self.annotation_table.columnCount() - 1:  # If the "+" column is clicked
            self.add_new_column()


    def add_new_column(self):
        column_name, ok = QInputDialog.getText(self, "New Column", "Enter column name:")
        if ok and column_name:
            current_column_count = self.annotation_table.columnCount()
            self.annotation_table.insertColumn(current_column_count)
            self.annotation_table.setHorizontalHeaderItem(current_column_count-1, QTableWidgetItem(column_name))
            self.custom_column_count += 1

            # Update the appropriate headers list
            if self.patient_level_radio.isChecked():
                self.patient_headers.insert(-1, column_name)
            else:
                self.record_headers.insert(-1, column_name)
            
            # Restore the last column's header item
            self.annotation_table.setHorizontalHeaderItem(current_column_count, QTableWidgetItem("+"))

            
            # Set the new column to be interactive and the last column (Annotation) to stretch
            header = self.annotation_table.horizontalHeader()
            header.setSectionResizeMode(current_column_count - 1, QHeaderView.Interactive)
            # header.setSectionResizeMode(current_column_count, QHeaderView.Stretch)

    def on_cell_changed(self, row, column):
        if not self.is_switching_levels and not self._is_updating:
            print(f"Cell changed: row {row}, column {column}")  # Debug print
            
            # Get the column name
            column_name = self.annotation_table.horizontalHeaderItem(column).text()
            # Check if the changed column is not "Comment"
            if column_name != "Comment":
                ## record and show time
                try:
                    self._is_updating = True
                    current_id = self.get_current_id()
                    if current_id in self.annotation_start_times:
                        start_time = self.annotation_start_times[current_id]
                        end_time = QDateTime.currentDateTime()
                        time_cost = start_time.secsTo(end_time)
                        time_cost_formatted = QTime(0, 0).addSecs(time_cost).toString('hh:mm:ss')
                        
                        # Update Time Cost column
                        self.annotation_table.setItem(row, self.get_column_index('Time Cost'), QTableWidgetItem(time_cost_formatted))
                        
                        # Update Annotation Start column
                        self.annotation_table.setItem(row, self.get_column_index('Annotation Start'), QTableWidgetItem(start_time.toString('yyyy-MM-dd hh:mm:ss')))
                        
                        # Update Annotation End column
                        self.annotation_table.setItem(row, self.get_column_index('Annotation End'), QTableWidgetItem(end_time.toString('yyyy-MM-dd hh:mm:ss')))
                        
                        # Reset start time for the next annotation
                        self.annotation_start_times[current_id] = end_time
                        # Reset current case start time
                        self.current_case_start_time = QDateTime.currentDateTime()
                    
                    self.save_current_annotations()
                finally:
                    self._is_updating = False
            else: ## if the edit is in comment column
                self.save_current_annotations()
            
    def get_column_index(self, column_name):
        headers = self.patient_headers if self.patient_level_radio.isChecked() else self.record_headers
        return headers.index(column_name)


    def save_current_annotations(self):
        is_patient_level = self.patient_level_radio.isChecked()
        headers = self.patient_headers if is_patient_level else self.record_headers
        for row in range(self.annotation_table.rowCount()):
            if is_patient_level:
                patient_id_item = self.annotation_table.item(row, 0)
                if patient_id_item is None:
                    continue  # Skip this row if there's no patient ID
                patient_id = patient_id_item.text()
                self.patient_annotations[patient_id] = {}
                for col, header in enumerate(headers[:-1]):  # Exclude the '+' column
                    item = self.annotation_table.item(row, col)
                    self.patient_annotations[patient_id][header] = item.text() if item else ''
                # print("Patient Annotations saved:", self.patient_annotations)  # Debug print
            else:
                patient_id_item = self.annotation_table.item(row, 0)
                record_id_item = self.annotation_table.item(row, 1)
                if patient_id_item is None or record_id_item is None:
                    continue  # Skip this row if there's no patient ID or record ID
                patient_id = patient_id_item.text()
                record_id = record_id_item.text()
                self.record_annotations[record_id] = {'PatientID': patient_id}
                for col, header in enumerate(headers[2:-1], start=2):  # Start from the third column, exclude '+'
                    item = self.annotation_table.item(row, col)
                    self.record_annotations[record_id][header] = item.text() if item else ''
                # print("Record Annotations saved:", self.record_annotations)  # Debug print


    def save_annotation_to_file(self):
        if not self.csv_file_path:
            self.csv_file_path, _ = QFileDialog.getSaveFileName(self, "Save Annotations", "", "CSV Files (*.csv)")
        
        if self.csv_file_path:
            try:
                with open(self.csv_file_path, 'w', newline='') as csvfile:
                    csv_writer = csv.writer(csvfile)
                    
                    # Write headers based on the selected annotation level
                    headers = self.patient_headers if self.patient_level_radio.isChecked() else self.record_headers
                    csv_writer.writerow(headers[:-1])  # Exclude the last "+" column

                    # Save patient-level annotations
                    if self.patient_level_radio.isChecked():
                        for record in self.records:
                            patient_id = record['PatientID']

                            # Default data for patient
                            row_data = [
                                patient_id,
                                str(len([r for r in self.records if r['PatientID'] == patient_id])),  # Record count
                                record.get('Record_Date', ''),  # Start date
                                record.get('Record_Date', ''),  # End date
                            ]

                            # Add annotation data if exists, else empty
                            annotations = self.patient_annotations.get(patient_id, {})
                            for header in self.patient_headers[4:-1]:  # Skip the first few and last '+' column
                                row_data.append(annotations.get(header, ''))

                            csv_writer.writerow(row_data)

                    # Save record-level annotations
                    else:
                        for record in self.records:
                            patient_id = record['PatientID']
                            record_id = record['RecordID']

                            # Default data for record
                            row_data = [
                                patient_id,
                                record_id,
                                record.get('Record_Date', ''),
                                record.get('Record_Type', ''),
                            ]

                            # Add annotation data if exists, else empty
                            annotations = self.record_annotations.get(record_id, {})
                            for header in self.record_headers[4:-1]:  # Skip the first few and last '+' column
                                row_data.append(annotations.get(header, ''))

                            csv_writer.writerow(row_data)

                QMessageBox.information(self, "Save Successful!", f"Annotations saved to {self.csv_file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Failed!", f"An error occurred while saving: {str(e)}")
        else:
            QMessageBox.warning(self, "Save Cancelled!", "Annotation saving was cancelled.")


    def save_project(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Project Files (*.proj)")
        if file_path:
            project_data = {
                'records': self.records,
                'filtered_records': self.filtered_records,
                'patient_annotations': self.patient_annotations,
                'record_annotations': self.record_annotations,
                'title_list': self.title_list,
                'patient_headers': self.patient_headers,
                'record_headers': self.record_headers,
                'load_keywords': self.load_keywords,
                'extend_keywords': self.extend_keywords,
                'total_time_cost': self.total_time_cost,
                'current_case_start_time': self.current_case_start_time,
                'annotation_start_times': self.annotation_start_times,
                # Add any other data you want to save
            }
            try:
                with open(file_path, 'wb') as f:
                    pickle.dump(project_data, f)
                QMessageBox.information(self, "Success", "Project saved successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save project: {str(e)}")


    def load_project(self):
        # The above Python code snippet is loading a project file using a file dialog (`QFileDialog`)
        # in a PyQt application. It reads the project data from the selected file using
        # `pickle.load`, which deserializes the data previously saved in the file.
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "Project Files (*.proj)")
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    project_data = pickle.load(f)
                print("Load file")
                # Restore project data
                self.records = project_data['records']
                self.filtered_records = project_data['filtered_records']
                self.patient_annotations = project_data['patient_annotations']
                self.record_annotations = project_data['record_annotations']
                self.title_list = project_data['title_list']
                self.patient_headers = project_data['patient_headers']
                self.record_headers = project_data['record_headers']
                self.load_keywords = project_data['load_keywords']
                self.extend_keywords = project_data['extend_keywords']
                self.total_time_cost = project_data['total_time_cost']
                self.current_case_start_time = project_data['current_case_start_time']
                self.annotation_start_times = project_data['annotation_start_times']
                # Restore any other data you saved
                # Update UI
                self.update_droplists()  ##TODO, when load stored project file, this function will be stucked.
                self.update_display()
                self.update_keyword_table()

                
                QMessageBox.information(self, "Success", "Project loaded successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load project: {str(e)}")


    # def start_annotation(self):
    #     if self.current_row is not None:
    #         self.start_time = QDateTime.currentDateTime()
    #         self.start_annotation_button.setEnabled(False)
    #         self.end_annotation_button.setEnabled(True)

    # def end_annotation(self):
    #     if self.start_time and self.current_row is not None:
    #         end_time = QDateTime.currentDateTime()
    #         time_cost = self.start_time.secsTo(end_time)
            
    #         # Format time cost as HH:MM:SS
    #         time_cost_formatted = QTime(0, 0).addSecs(time_cost).toString('hh:mm:ss')
    #         self.annotation_table.setItem(self.current_row, 4, QTableWidgetItem(time_cost_formatted))
            
    #         self.start_time = None
    #         self.start_annotation_button.setEnabled(True)
    #         self.end_annotation_button.setEnabled(False)

    # def save_text_change(self, annotation_text):
    #     if self.current_row is not None and self.csv_file_path:
    #         self.annotation_table.setItem(self.current_row, 5, QTableWidgetItem(annotation_text))
    #         self.save_to_csv()

    # def save_to_csv(self):
    #     if self.csv_file_path:
    #         with open(self.csv_file_path, 'w', newline='') as csvfile:
    #             csv_writer = csv.writer(csvfile)
    #             csv_writer.writerow([self.annotation_table.horizontalHeaderItem(i).text() for i in range(self.annotation_table.columnCount())])
    #             for row in range(self.annotation_table.rowCount()):
    #                 row_data = []
    #                 for col in range(self.annotation_table.columnCount()):
    #                     item = self.annotation_table.item(row, col)
    #                     row_data.append(item.text() if item else '')
    #                 csv_writer.writerow(row_data)

## place holder if text edit is needed
class AnnotationTextEdit(QTextEdit):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        # self.textChanged.connect(self.on_text_changed)
        self.last_text = ""

    # def on_text_changed(self):
    #     current_text = self.toPlainText()
    #     if current_text != self.last_text:
    #         self.parent.save_text_change(current_text)
    #         self.last_text = current_text

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AnnotationTool()
    ex.show()
    sys.exit(app.exec_())