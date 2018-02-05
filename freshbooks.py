# encoding: utf-8

import os
import sys
import subprocess
import curses
import curses.ascii
import string
import random
import datetime
import xmltodict
import requests
import argparse
import npyscreen
import time

from difflib import get_close_matches, SequenceMatcher
from easydict import EasyDict as edict
from settings import API_TOKEN, API_URL


session = requests.Session()
session.auth = (API_TOKEN, 'X')

def request_api(data):
    r = None
    done = False
    while not done:
        try:
            r = session.get(API_URL, data=data)
            done = True
        except Exception:
            # Retrying
            time.sleep(1)
    
    return  edict(xmltodict.parse(r.text))

cache = {}


def get_projects(as_dict=False):
    def _to_dict(projects):
        return dict([ p[:2] for p in projects ])

    if "get_projects" in cache:
        if as_dict:
            return _to_dict(cache["get_projects"])
        return cache["get_projects"]
    r = None
    done = False
    while not done:
        try:
            r = session.get(API_URL, data='<?xml version="1.0" encoding="utf-8"?><request method="project.list"></request>')
            done = True
        except Exception:
            print("Retrying")
            time.sleep(1)
    d = edict(xmltodict.parse(r.text))

    data = []
    for project in d.response.projects.project:
        data.append(
            [project.project_id, project.name,  [task.task_id for task in project.tasks.task] ]
        )
    # project
    # id, name, tasks allowed
    cache["get_projects"] = data
    if as_dict:
        return _to_dict(cache["get_projects"])
    return data


def get_tasks(project_id=None):
    key = "get_tasks"+str(project_id)
    if key in cache:
        return cache[key]
  
    if project_id is None:
        data = '<?xml version="1.0" encoding="utf-8"?><request method="task.list"></request>'
    else:
        data = '<?xml version="1.0" encoding="utf-8"?><request method="task.list"><project_id>%s</project_id></request>' % project_id

    r = None
    done = False
    while not done:
        try:
            r = session.get(API_URL, data=data)
            done = True
        except Exception:
            print("Retrying")
            time.sleep(1)
    
    d = edict(xmltodict.parse(r.text))
    data = [ ( task["task_id"], task["name"] ) for task in d["response"]["tasks"]["task"] ]
    cache[key] = data
    return data


def get_time_entry_list(date_from, date_to, page=1):
    date_from = date_from.strftime("%Y-%m-%d")
    date_to = date_to.strftime("%Y-%m-%d")

    data = '<?xml version="1.0" encoding="utf-8"?>'+\
            '<request method="time_entry.list">'+\
               ('<page>%s</page>' % page)+\
               ('<date_from>%s</date_from>' % date_from)+\
               ('<date_to>%s</date_to>' % date_to)+\
            '</request>'

    d = request_api(data)

    time_entries_result = []
    time_entries = d.response.time_entries.get("time_entry", [])

    if not isinstance(time_entries, list):
        time_entries = [time_entries]

    for time_entry in time_entries:
        te = TimeEntry()
        te.load_from_entry_dict(time_entry)
        time_entries_result.append(te)

    return time_entries_result


class TimeEntry(object):
    def __init__(self):
        self.time_entry_id = None
        self.project_id = None
        self.task_id = None
        self.hours = 1
        self.notes = ""
        self.date = datetime.date.today()

    def to_dict(self):
        d = dict(
            hours=self.hours,
            notes=self.notes,
            date=self.date.isoformat()
        )
        if self.time_entry_id is not None:
            d["time_entry_id"] = self.time_entry_id

        if self.project_id is not None:
            d["project_id"] = self.project_id

        if self.task_id is not None:
            d["task_id"] = self.task_id

        return d

    def load_from_entry_dict(self, time_entry):
        for key, val in time_entry.items():
            if val is not None:
                if key == "hours":
                    setattr(self, key, float(val))
                else:
                    setattr(self, key, val)
        self.date = datetime.datetime.strptime(self.date.split(" ")[0], "%Y-%m-%d").date()

    def load(self):
        data = '<?xml version="1.0" encoding="utf-8"?><request method="time_entry.get"><time_entry_id>%s</time_entry_id></request>' % self.time_entry_id
        d = request_api(data)
        self.load_from_entry_dict(d.response.time_entry)

    def save(self):
        #print("Saving...")
        task = {
            'request': {
                '@method': 'time_entry.create',
                'time_entry': self.to_dict()
            }
        }

        if self.time_entry_id is not None:
            task["request"]["time_entry"]["time_entry_id"] = self.time_entry_id
            task["request"]["@method"] = "time_entry.update"
        
        r = None
        done = False
        while not done:
            try:
                r = session.get(API_URL, data=xmltodict.unparse(task))
                done = True
            except Exception:
                print("Retrying")
                time.sleep(1)
        
        #if self.time_entry_id is not None:
            #print("Time entry updated ", self.time_entry_id)
        #else:
            #print("Time entry created: ", edict(xmltodict.parse(r.text))["response"]["time_entry_id"])


class AutocompleteChoices(npyscreen.Autocomplete):
    def __init__(self, *args, **kwargs):
        super(AutocompleteChoices, self).__init__(*args, **kwargs)
        self.choices = None

    def auto_complete(self, input_ch):
        #if self.choices is None:
        self.choices = self.parent_widget.get_choices_list()

        matches = []

        user_input = self.value.lower().strip()
        if user_input is None or user_input == "":
            matches = self.choices[:]
        else:
            # filter choices
            results = {}
            for pid, name in self.choices:
                results[
                    SequenceMatcher(None, user_input, name.lower()).ratio()
                ] = (pid, name)
            results_keys = list(results.keys())
            results_keys.sort()
            results_keys.reverse()
            for key in results_keys:
                matches.append(results[key])

        if len(matches) == 1:
            self.real_value = matches[0]
            self.value = self.real_value[1]
        elif len(matches) == 0:
            self.real_value = self.choices[
                self.get_choice(
                    [x[1] for x in self.choices]
                )
            ]
            self.value = self.real_value[1]
        else:
            self.real_value = matches[
                self.get_choice(
                    [ x[1] for x in matches ]
                )
            ]
            self.value = self.real_value[1]


class TitleAutocomplete(npyscreen.wgtitlefield.TitleText):
    _entry_type = AutocompleteChoices

    def __init__(self, *args, **kwargs):
        self.real_value = kwargs.pop("real_value",None)
        super(TitleAutocomplete, self).__init__(*args, **kwargs)

        if isinstance(self.real_value, tuple) or isinstance(self.real_value, list):
            self.value = self.real_value[1]
            self.entry_widget.real_value = self.real_value

    def set_choice_value(self, real_value):
        self.real_value = real_value
        self.value = self.real_value[1]
        self.entry_widget.real_value = self.real_value

    def get_choice_value(self):
        try:
            return self.entry_widget.real_value
        except AttributeError:
            return None


class TitleAutocompleteProject(TitleAutocomplete):
    def get_choices_list(self):
        return list(get_projects(as_dict=True).items())


class TitleAutocompleteTask(TitleAutocomplete):
    def get_choices_list(self):
        try:
            allowed_tasks = list(filter(lambda x:x[1] == self.parent.project.value, get_projects()))[0][2]
        except IndexError:
            return get_tasks()
        return list(filter(lambda x:x[0] in allowed_tasks, get_tasks()))


class TimeEntryForm(npyscreen.ActionForm):
    def __init__(self, *args, time_entry=None, **kwargs):
        super(TimeEntryForm, self).__init__(*args, **kwargs)
        if time_entry is not None:
            self.time_entry = time_entry

            if time_entry.time_entry_id is not None:
                self.project.set_choice_value((
                    time_entry.project_id, get_projects(as_dict=True).get(time_entry.project_id)
                ))
                self.task.set_choice_value((
                    time_entry.task_id, dict(get_tasks()).get(time_entry.task_id)
                ))
                self.date.value = time_entry.date
                self.hours.value = time_entry.hours
                self.notes.value = time_entry.notes

    def create(self):
        self.project = self.add(TitleAutocompleteProject, name="Project:", scroll_exit=True)
        self.task = self.add(TitleAutocompleteTask, name="Task:", scroll_exit=True)
        self.date = self.add(npyscreen.TitleDateCombo, value=datetime.date.today(), name="Date:")
        self.hours = self.add(npyscreen.TitleSlider, value=4, out_of=10, step=0.25, name="Time:")
        self.add(npyscreen.TitleFixedText, name="Notes:")
        self.notes = self.add(npyscreen.MultiLineEdit, value="""Notes here...\n""", max_height=10, rely=7, )

    def on_ok(self):
        self.time_entry.project_id = self.project.get_choice_value()[0]
        self.time_entry.task_id = self.task.get_choice_value()[0]
        self.time_entry.hours = self.hours.value
        self.time_entry.notes = self.notes.value
        self.time_entry.date = self.date.value
        self.time_entry.save()


class KeyValueGrid(npyscreen.SimpleGrid):
    def __init__(self, *args, **kwargs):
        key_enter_callback = kwargs.pop("key_enter_callback", None)
        super(KeyValueGrid, self).__init__(*args, **kwargs)
        self.values = []
        self.values_data = []
        self.key_enter_callback = None
        if key_enter_callback is not None:
            self.key_enter_callback = key_enter_callback

    def set_up_handlers(self):
        super(KeyValueGrid, self).set_up_handlers()
        self.handlers[curses.ascii.NL] = self.h_key_enter

    def h_key_enter(self, input):
        if self.key_enter_callback:
            self.key_enter_callback(self)

    def get_value_display(self):
        return self.values[
            self.edit_cell[0]
        ][
            self.edit_cell[1]
        ]

    def get_value_data(self):
        return self.values_data[
            self.edit_cell[0]
        ][
            self.edit_cell[1]
        ]


class CalendarGrid(KeyValueGrid):
    default_column_number = 7

    def do_calendar(self, from_date, to_date):
        t = datetime.date.today()

        cur_date = from_date

        # move back until it is sunday
        # Monday 0 Sunday 6.
        while cur_date.weekday() != 6:
            cur_date -= datetime.timedelta(days=1)

        self.values = []
        self.values_data = []
        self.values_data = [[None] * 7]
        self.values.append([
            "Sun",
            "Mon",
            "Tues",
            "Wed",
            "Thurs",
            "Fri",
            "Sat"
        ])

        while cur_date < to_date:
            row = []
            row_data = []
            for y in range(7):
                row.append(cur_date.day)
                row_data.append(cur_date)
                cur_date += datetime.timedelta(days=1)

            self.values.append(row)
            self.values_data.append(row_data)


    def get_value_display(self):
        return self.values[
            self.edit_cell[0]
        ][
            self.edit_cell[1]
        ]

    def get_value_data(self):
        return self.values_data[
            self.edit_cell[0]
        ][
            self.edit_cell[1]
        ]


class DaysForm(npyscreen.ActionForm):
    def create(self):
        #tel = get_tasks_list()
        self.add(npyscreen.TitleFixedText, name="Today is %s" % datetime.date.today().isoformat())
        self.add(npyscreen.TitleFixedText, name="------")
        self.calendar = self.add(CalendarGrid, key_enter_callback=self.selected_date)
        self.time_entry_list = self.add(KeyValueGrid, columns=1, key_enter_callback=self.selected_time_entry)
        self.time_entry_list.values = [["h"],["h"],["h"],["h"]]
        today = datetime.datetime.today()
        month_start = datetime.date(today.year, today.month, 1)

        #self.time_entries = get_time_entry_list(date_from=month_start, date_to=month_start+datetime.timedelta(days=30))

        self.calendar.do_calendar(
            from_date=month_start,
            to_date=month_start + datetime.timedelta(days=30)
        )

    def selected_time_entry(self, time_entry_list):
        pass

    def selected_date(self, calendar):
        date = calendar.get_value_data()
        self.time_entry_list.values = []
        self.time_entry_list.values_data = []

        for x in range(date.day):
            self.time_entry_list.values.append([str(x)])
            self.time_entry_list.values_data.append([str(x)])

        #self.time_entries = filter(
            # lambda x: x.date == date,
            # self.time_entries
        # )

    def on_ok(self):
        pass


def clear():
    if os.name in ('nt','dos'):
        subprocess.call("cls")
    elif os.name in ('linux','osx','posix'):
        subprocess.call("clear")
    else:
        print("\n"*200)


class TestApp(npyscreen.NPSApp):
    def __init__(self, *args, **kwargs):
        self.edit_time_entry_id = None

    def edit(self, te):
        form = TimeEntryForm(time_entry=te)
        form.edit()
    
    def list(self):
        form = DaysForm()
        form.edit()

    def main(self):
        # These lines create the form and populate it with widgets.
        # A fairly complex screen in only 8 or so lines of code - a line for each control.
        # This lets the user interact with the Form.
        if self.edit_time_entry_id is not None:
            te = TimeEntry()
            te.time_entry_id = self.edit_time_entry_id
            te.load()
        else:
            te = TimeEntry()

        self.edit(te)


if __name__ == "__main__":
    projects = get_projects(as_dict=True)
    tasks = dict(get_tasks())
    app = TestApp()

    while True:
        app.edit_time_entry_id = None
        today = datetime.datetime.today()
        clear()
        print("Today is %s" % today.isoformat())
        print("0 - Add")

        month_start = datetime.date(today.year, today.month, 1)
        time_entries = get_time_entry_list(date_from=today-datetime.timedelta(days=6), date_to=today)

        print("---------------")
        today = time_entries[0].date.day if time_entries else 0

        day_hours = 0
        for idx, te in enumerate(time_entries, 1):
            if today != te.date.day:
                print("--------------- worked %s hours" % (day_hours,))
                print("")
                day_hours = 0
                today = te.date.day
            day_hours += te.hours
            print(
                "%s - %s %s %s %sh (%s)" % (
                    idx,
                    te.date.strftime("%d %B, %Y"),
                    projects.get(te.project_id),
                    tasks.get(te.task_id),
                    te.hours,
                    te.time_entry_id
                )
            )

        try:
            entry = int(input(">"))
        except:
            print("------ done ------")
            sys.exit(0)

        if entry > 0:
            app.edit_time_entry_id = time_entries[entry-1].time_entry_id

        app.run()
