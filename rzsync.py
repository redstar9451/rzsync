#!/usr/bin/env python3
# encoding:utf-8

import sys
import os
import time
import hashlib
import shutil
import tempfile
import re
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
from jinja2 import Environment, BaseLoader


class EventHandler(FileSystemEventHandler):
    def __init__(self, *args, base_path='', **kwargs):
        super().__init__(*args, **kwargs)

        self.file_change_list = {}
        self.folder_change_list = {}
        self.base_path = base_path

    def is_ignored(self, src_path) -> bool:
        ignore_list = [
            r'mysync\.sh',
            r'sync\.tar\.gz',
            r'\..*',
        ]

        if src_path in ['.', '..', self.base_path]:
            return True

        src_path = src_path.replace(self.base_path + '/', '')
        for item in ignore_list:
            if re.match(item, src_path) is not None:
                return True

        return False

    # using 'dcit' to do hash store
    def add_change(self, event):
        if self.is_ignored(event.src_path):
            return

        if event.is_directory:
            self.folder_change_list[event.src_path] = 'whatever'
        else:
            self.file_change_list[event.src_path] = 'whatever'

    def on_moved(self, event):
        if self.is_ignored(event.src_path):
            return

        if event.is_directory:
            self.folder_change_list[event.src_path] = 'whatever'
            self.folder_change_list[event.dest_path] = 'whatever'
        else:
            self.file_change_list[event.src_path] = 'whatever'
            self.file_change_list[event.dest_path] = 'whatever'

        super().on_moved(event)

    def on_created(self, event):
        # echo hello world > 1.txt, 1.txt will be create then modified
        self.add_change(event)
        super().on_created(event)

    def on_deleted(self, event):
        self.add_change(event)
        super().on_deleted(event)

    def on_modified(self, event):
        # for directory, ignore modified event
        if not event.is_directory:
            self.add_change(event)
        super().on_modified(event)

    def _md5sum(self, f):
        with open(f, 'rb') as rf:
            file_content = rf.read()
            rf.close()
        m = hashlib.md5()
        m.update(file_content)
        return m.hexdigest()

    def generate_snapshot(self):
        bash_script = '''
#!/bin/bash
# prepare
mkdir .sync
sed -e '1,/^%%HELLO%%$/d' $0 | tar xzf - -C .sync || exit 1

# sync folder first
{% for folder,value in folders.items() %}
{% if value['action'] == 'create_or_modify' %}
if [ ! -d {{ folder }} ]; then
    echo mkdir -p {{ folder }}
    mkdir -p {{ folder }}
fi
{% else %}
if [ -e {{ folder }} ]; then
echo rm -rf {{ folder }}
rm -rf {{ folder }}
fi
{% endif %}
{% endfor %}

# then sync files
{% for f,value in files.items() %}
{% if value['action'] == 'create_or_modify' %}
echo cp ./.sync/{{ value['extension'] }} {{ f }}
cp ./.sync/{{ value['extension'] }} {{ f }}
{% else %}
if [ -e {{ f }} ]; then
echo rm -rf {{ f }}
rm -rf {{ f }}
fi
{% endif %}
{% endfor %}

# clean
rm -rf ./.sync
echo "sync done"
exit 0
# end marker
%%HELLO%%

'''
        folder_change_list = self.folder_change_list
        self.folder_change_list = {}

        folder_change_trim = {}
        for folder in folder_change_list.keys():
            if Path(folder).exists():
                folder_change_trim[folder.replace(self.base_path, '.')] = {
                    'action': 'create_or_modify',
                    'extension': None
                }
            else:
                folder_change_trim[folder.replace(self.base_path, '.')] = {
                    'action': 'delete',
                    'extension': None
                }

        for folder, v in folder_change_trim.items():
            print("{}: {} folder".format(folder, v['action']))

        file_change_trim = {}
        with tempfile.TemporaryDirectory() as tmpdirname:
            file_change_list = self.file_change_list
            self.file_change_list = {}

            for f in file_change_list.keys():
                if Path(f).exists():
                    md5 = self._md5sum(f)
                    shutil.copy(f, Path(tmpdirname, md5))
                    file_change_trim[f.replace(self.base_path, '.')] = {
                        'action': 'create_or_modify',
                        'extension': md5
                    }
                else:
                    file_change_trim[f.replace(self.base_path, '.')] = {
                        'action': 'delete',
                        'extension': None
                    }
            for f, v in file_change_trim.items():
                print("{}: {} file".format(f, v['action']))

            tar_file = Path(self.base_path, 'sync')
            shutil.make_archive(tar_file, "gztar", tmpdirname)

        rtemplate = Environment(loader=BaseLoader).from_string(bash_script)
        args = {"folders": folder_change_trim, "files": file_change_trim}
        output = rtemplate.render(**args)

        return output


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    print("working directory is : " + path)

    event_handler = EventHandler(base_path=path)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()

    try:
        while True:
            print("\nPress Enter to generate sync shell script")
            input()
            shell_script = event_handler.generate_snapshot()
            f = open('./mysync.sh', 'wb')
            f.write(shell_script.encode(encoding="utf-8"))
            tar_file = Path(path, 'sync.tar.gz')
            with open(tar_file, 'rb') as tar:
                f.write(tar.read())
                tar.close()
            f.close()
            os.remove(tar_file)
            time.sleep(1)
            print("generate mysync.sh done")
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

