from os import system
import system_calls
from backend.dataManager.dataManager import DataManager
from backend import models
import json
import csv


class SysCallManager(DataManager):
    def __init__(self, socketio, db):
        super().__init__(socketio, db)
        self.syscalls = system_calls.syscalls()

        self.reads_vs_writes = {}

        self.directory_frequency = {}

    def setup_data_structures(self, sandbox_id):
        self.reads_vs_writes[sandbox_id] = {
            "healthy": {"graph": {"reads": 0, "writes": 0}}, "infected": {"graph": {"reads": 0, "writes": 0}}}
        self.directory_frequency[sandbox_id] = {
            "healthy": {"graph": {"/": {"n": 0, "sd": []}}}, "infected": {"graph": {"/": {"n": 0, "sd": []}}}}

    def process_data(self, data, architecture):
        syscall_list = []
        for syscall in data.splitlines():
            processed_system_call = self.process_syscall(syscall, architecture)
            if processed_system_call:
                syscall_list.append(processed_system_call)
        return syscall_list

    def handle_message(self, data):
        print("Processing Received Syscalls...")
        for infected_status in data["sysCalls"].keys():
            data["sysCalls"][infected_status] = self.process_data(
                data["sysCalls"][infected_status], data["architecture"])

        sandbox_id = data["ID"]

        # Call extract functions here
        print("Extracting Graphs...")
        self.extract_graphs(sandbox_id, data)
        # Call emit functions here

        self.save_data(data)
        return True

    def get_name_from_no(self, sysno, architecture):
        names = list(self.syscalls.syscalls["archs"][architecture].keys())
        index = list(
            self.syscalls.syscalls["archs"][architecture].values()).index(sysno)
        return names[index]

    def process_syscall(self, syscall, architecture):
        components = syscall.split()
        if not syscall.__contains__("sysno"):
            components.insert(16, "sysno:")
            components.insert(17, "0")
        args = []

        time_index = components.index("time_ns:") + 1
        thread_index = components.index("thread_id:") + 1
        sysno_index = components.index("sysno:") + 1
        container_id_index = components.index("container_id:") + 1
        cwd_index = components.index("cwd:") + 1

        credentials_indexes = [components[container_id_index:cwd_index].index("{"), components[container_id_index:cwd_index].index("}")]

        time = int(components[time_index])
        thread = int(components[thread_index])
        sysno = int(components[sysno_index])
        sysname = self.get_name_from_no(sysno, architecture)
        container_id = components[container_id_index]
        cwd = components[cwd_index]
        cred = str(components[credentials_indexes[0]:credentials_indexes[1]]).replace(",", " ")

        for i in range(len(components[sysno_index:])):
            if i % 2 == 1:
                args.append(components[sysno_index:][i+1])

        processed_system_call = {
                "time_ns": time,
                "thread_id": thread,
                "sysno": sysno,
                "sysname": sysname,
                "container_id": container_id,
                "cwd": cwd,
                "credentials": cred,
                "args": str(args).replace(",", ";")
        }
        return processed_system_call

    def save_data(self, data):
        print("Saving Syscall Data: " + data["ID"])

        i = data["ID"]
        print(self.reads_vs_writes[i])
        pm = models.SystemCallModel(
            ID=i,
            reads_vs_writes=json.dumps(self.reads_vs_writes[i]),
            directory_frequency=json.dumps(self.directory_frequency[i])
        )
        pm.save()
        ID = data["ID"]
        for infected_status in data["sysCalls"].keys():
            file_path = infected_status + '/' + str(ID) + '.csv'
            with open(file_path, "w+", newline="") as f:
                title = "time_ns,thread_id,sysno,sysname,container_id,cwd,credentials,args".split(
                    ",")
                cw = csv.DictWriter(f, title, delimiter=',',
                                    quotechar='|', quoting=csv.QUOTE_MINIMAL)
                cw.writeheader()
                cw.writerows(data["sysCalls"][infected_status])
            print("Done!")

    def extract_graphs(self, sandbox_id, data):
        self.reads_vs_writes[sandbox_id] = {
            "healthy": {"graph": {"reads": 0, "writes": 0}}, "infected": {"graph": {"reads": 0, "writes": 0}}}
        self.directory_frequency[sandbox_id] = {
            "healthy": {"graph": {"/": {"n": 0, "sd": []}}}, "infected": {"graph": {"/": {"n": 0, "sd": []}}}}

        for infected_status in data["sysCalls"]:
            for syscall in data["sysCalls"][infected_status]:
                self.extract_read_vs_writes(
                    syscall, sandbox_id, infected_status)
                self.extract_directory_frequency(
                    syscall, sandbox_id, infected_status)

    def extract_read_vs_writes(self, syscall, sandbox_id, infected_status):
        if syscall["sysname"] == "read":
            self.reads_vs_writes[sandbox_id][infected_status]["graph"][
                "reads"] = self.reads_vs_writes[sandbox_id][infected_status]["graph"]["reads"] + 1
        if syscall["sysname"] == "write":
            self.reads_vs_writes[sandbox_id][infected_status]["graph"][
                "writes"] = self.reads_vs_writes[sandbox_id][infected_status]["graph"]["writes"] + 1

    def extract_directory_frequency(self, syscall, sandbox_id, infected_status):
        directories = syscall["cwd"].replace('"', '').split("/")
        directories = list(filter(lambda a: a != '', directories))
        self.directory_frequency[sandbox_id][infected_status]["graph"]["/"]["n"] += 1
        self.insert_into_tree(
            self.directory_frequency[sandbox_id][infected_status]["graph"], directories)

    def find_in_list(self, directory, list):
        for i in range(len(list)):
            if directory in list[i].keys():
                return i
        return -1

    def insert_into_tree(self, tree, directories):
        if len(directories) == 0:
            return tree
        current_directory = directories[0]
        previous_dir = list(tree.keys())[0]
        index = self.find_in_list(current_directory, tree[previous_dir]["sd"])
        if index == -1:
            subdir_structure = {current_directory: {"n": 0,
                                "sd": []}}
            tree[previous_dir]["sd"].append(subdir_structure)
            index = self.find_in_list(
                current_directory, tree[previous_dir]["sd"])
        if len(directories) == 1:
            tree[previous_dir]["sd"][index][current_directory]["n"] += 1
        try:
            subtree = tree[previous_dir]["sd"][index]
            tree[previous_dir]["sd"][index] = self.insert_into_tree(
                subtree, directories[1:])
            return tree
        except IndexError:
            tree["sd"] = []
            return tree
