#!/usr/bin/python3

import sys
import os
import time
import logging
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class EventHandler(FileSystemEventHandler):
    def __init__(self, *args, ignore=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.file_change_list = {}
        self.folder_change_list = {}

    def is_ignored(self, src_path) -> bool:
        if src_path in ('./sync.pipe', '.'):
            return True

        return False

    def add_change(self, event):
        if event.is_directory:
            self.folder_change_list[event.src_path] = 'whatever'
        else:
            self.file_change_list[event.src_path] = 'whatever'


    def on_moved(self, event):
        src_path = event.src_path
        if self.is_ignored(src_path):
            return

        if event.is_directory:
            self.folder_change_list[event.src_path] = 'whatever'
            self.folder_change_list[event.dest_path] = 'whatever'
        else:
            self.file_change_list[event.src_path] = 'whatever'
            self.file_change_list[event.dest_path] = 'whatever'

        super().on_moved(event)


    def on_created(self, event):
        src_path = event.src_path
        if self.is_ignored(src_path):
            return

        # echo hello world > 1.txt, 1.txt will be create then modified
        self.add_change(event)

        super().on_created(event)

    def on_deleted(self, event):
        src_path = event.src_path
        if self.is_ignored(src_path):
            return

        self.add_change(event)

        super().on_deleted(event)


    def on_modified(self, event):
        src_path = event.src_path
        if self.is_ignored(src_path):
            return

        self.add_change(event)

        super().on_modified(event)

def generate_snapshot(folder_change_list, file_change_list):

    extract_cmd = '''#!/bin/bash
sed -e '1,/^%%FUCK%%$/d' $0| tar xjf - || exit 1
'''

    mkdir_cmd = '''
if [ ! -d <replace> ]; then
    echo mkdir -p <replace>
    mkdir -p <replace>
fi
'''
    rm_cmd = '''
if [ -e <replace> ]; then
echo rm -rf <replace>
rm -rf <replace>
fi
'''

    write_file_cmd = '''
echo cp <replace1> <replace2>
cp <replace1> <replace2>
    '''

    finish_cmd = '''
echo "sync done"
exit 0
%%FUCK%%
'''

    output = extract_cmd

    for folder in folder_change_list.keys():
        if os.path.exists(folder):
            cmd = mkdir_cmd.replace('<replace>', folder)
        else:
            cmd = rm_cmd.replace('<replace>', folder)

        output = output + cmd

    for f in file_change_list.keys():
        if os.path.exists(f):
            with open(f, 'rb') as rf:
                file_content = rf.read()
                rf.close()

            m = hashlib.md5()
            m.update(file_content)
            new_file = '.sync/' + m.hexdigest()

            with open(new_file, 'wb') as wf:
                wf.write(file_content)
                wf.close()

            cmd = write_file_cmd.replace('<replace1>', new_file)
            cmd = cmd.replace('<replace2>', f)
        else:
            cmd = rm_cmd.replace('<replace>', f)

        output = output + cmd
    output = output + finish_cmd
    return output

if __name__ == "__main__":
    print("server started")
    if os.path.exists('./sync.pipe') is False:
        os.system('mkfifo sync.pipe')

    if os.path.exists('.sync'):
        os.system('rm -rf .sync')
    os.system('mkdir .sync')

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'

    event_handler = EventHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            f = open('./sync.pipe', 'wb') # for pipe file, sleep here until another process read the pipe file
            file_change_list = event_handler.file_change_list
            folder_change_list = event_handler.folder_change_list
            event_handler.file_change_list = {}
            event_handler.folder_change_list = {}
            output = generate_snapshot(folder_change_list, file_change_list)
            os.system('tar cjf sync.tar.bz2 .sync')
            f.write(output.encode(encoding="utf-8"))
            #os.system('cat sync.tar.bz2 >> ./sync.pipe')
            with open('sync.tar.bz2', 'rb') as tar:
                f.write(tar.read())
                tar.close()
            f.close()
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
