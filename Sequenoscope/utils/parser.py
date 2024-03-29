#!/usr/bin/env python
from __future__ import print_function
from Sequenoscope.utils.__init__ import is_non_zero_file
import pandas as pd
import json
import re
import os
import sys

class GeneralSeqParser:
    file = None
    file_type = None
    parsed_file = None
    
    def __init__(self, file, file_type):
        self.file = file
        self.file_type = file_type
        if file_type == "tsv":
            self.parse_tsv()
        if file_type == "json":
            self.parse_json()
        if file_type == "csv":
            self.parse_csv()
        if file_type == "seq_summary":
            self.file_parsing_precheck(file, list_of_headers=["read_id", "channel", "start_time", "duration", "sequence_length_template", "mean_qscore_template", "end_reason"] )
            self.parse_seq_summary()
        pass

    def parse_tsv(self):
        self.parsed_file = pd.read_csv(self.file, sep='\t', header=0, index_col=0)
        

    def parse_json(self):
        self.parsed_file = json.load(open(self.file))

    def parse_csv(self):
        self.parsed_file = pd.read_csv(self.file)

    def parse_seq_summary(self):
        self.parsed_file = pd.read_csv(self.file, sep='\t', index_col=0)
        self.parsed_file = self.parsed_file[["read_id", "channel", "start_time", "duration", "sequence_length_template", "mean_qscore_template", "end_reason"]]
        self.parsed_file.reset_index(drop=True, inplace=True)

    def file_parsing_precheck(self, file_path, delemiter="\t", list_of_headers=None):
        if not is_non_zero_file(file_path):
            raise ValueError("Error: file not found")
        
        df = pd.read_csv(file_path, delimiter=delemiter)

        if list_of_headers is not None:
            if not set(list_of_headers).issubset(set(df.columns)):
                raise ValueError("Error: column headers did not match expected output. check file.")
        
        return True
    
class fastq_parser:
    REGEX_GZIPPED = re.compile(r'^.+\.gz$')
    f = None
    read_id_from_record = None
    def __init__(self,filepath):
        self.filepath = filepath

    def parse(self):
        filepath  = self.filepath
        if self.REGEX_GZIPPED.match(filepath):
            # using os.popen with zcat since it is much faster than gzip.open or gzip.open(io.BufferedReader)
            # http://aripollak.com/pythongzipbenchmarks/
            # assumes Linux os with zcat installed
            with os.popen('zcat < {}'.format(filepath)) as f:
                yield from self.parse_fastq(f)
        else:
            with open(filepath, 'r') as f:
                yield from self.parse_fastq(f)
        return


    def parse_fastq(self,f):

        record = []
        n = 0
        for line in f:
            n += 1
            record.append(line.rstrip())
            if n == 4:
                self.read_id_from_record = record[0].split(" ")[0][1:]
                yield record
                n = 0
                record = []

class FastqPairedEndRenamer:
    out_prefix = None
    out_dir = None
    read_set = None
    status = False
    result_files = {"fastq_file_renamed":[]}

    def __init__(self, read_set, read_file, out_dir, out_prefix):
        """
        Initalize the class with read_set, out_prefix, and out_dir

        Arguments:
            read_set: sequence object
                an object that contains the list of sequence files for analysis
            read_file: str
                path with the list of extracted reads from original fastq files
            out_prefix: str
                a designation of what the output files will be named
            out_dir: str
                a string to the path where the output files will be stored
        """
        self.out_prefix = out_prefix
        self.out_dir = out_dir
        self.read_set = read_set
        self.read_file = read_file
        self.read_list = set()
        self.read_id_list()

    def read_id_list(self):
        """
        Extracts all read ids from the read file into a set
        """
        with open(self.read_file, 'r') as f:
            for read_id in f:
                self.read_list.add(read_id)

    def rename(self):
        """
        creates a copy of each fastq files, extracts the name of the read id and sequence information,
        appends 1 or 2 to the end of the read id name, and checks if the file was created

        Returns:
            bool:
                returns True if the generated output file is found and not empty, False otherwise
        """
        for file_num in [0, 1]:
            line_id = 0
            name = ''
            data = ''
            qual = ''
            valid = False
            out_file = open(f"{self.out_dir}/{self.out_prefix}_{file_num+1}.fastq", "w")
            fastq_out_file = os.path.join(self.out_dir,"{}_{}.fastq".format(self.out_prefix, file_num+1))
            self.result_files["fastq_file_renamed"].append(fastq_out_file)
            with open(self.read_set.files[file_num], 'r') as f:
                for line in f:
                    if (line_id == 0):
                        if (valid):
                            if (len(name) == 0 or len(data) == 0 or len(data) != len(qual)):
                                print('File is not in FASTQ format')
                                sys.exit(1)
                            valid = False
                            if (name in self.read_list):
                                out_file.write(name + '2\n')
                            else:
                                self.read_list.add(name)
                                out_file.write(name + f'{file_num+1}\n')
                            out_file.write(data + '\n')
                            out_file.write('+' + '\n')
                            out_file.write(qual + '\n')
                        name = line.rstrip().split(' ')[0]
                        data = ''
                        qual = ''
                        line_id = 1
                    elif (line_id == 1):
                        if (line[0] == '+'):
                            line_id = 2
                        else:
                            data += line.rstrip()
                    elif (line_id == 2):
                        qual += line.rstrip()
                        if (len(qual) >= len(data)):
                            valid = True
                            line_id = 0

            if (valid):
                if (len(name) == 0 or len(data) == 0 or len(data) != len(qual)):
                    print(len(name), len(data), len(qual))
                    print('File is not in FASTQ format')
                    sys.exit(1)
                if (name in self.read_list):
                    out_file.write(name + '2\n')
                else:
                    self.read_list.add(name)
                    out_file.write(name + f'{file_num+1}\n')
                    out_file.write(data + '\n')
                    out_file.write('+' + '\n')
                    out_file.write(qual + '\n')

            self.status = self.check_files(fastq_out_file)
            if self.status == False:
                self.error_messages = "one or more files was not created or was empty, check error message\n{}".format(self.stderr)
                raise ValueError(str(self.error_messages))

            out_file.close()

    def check_files(self, files_to_check):
        """
        check if the output file exists and is not empty

        Arguments:
            files_to_check: list
                list of file paths

        Returns:
            bool:
                returns True if the generated output file is found and not empty, False otherwise
        """
        if isinstance (files_to_check, str):
            files_to_check = [files_to_check]
        for f in files_to_check:
            if not os.path.isfile(f):
                return False
            elif os.path.getsize(f) == 0:
                return False
        return True