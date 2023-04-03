#!/usr/bin/env python

import statistics
import pysam
from Sequenoscope.utils.__init__ import run_command, is_non_zero_file

class bam:

    alignment_file = None
    index_file = None
    pysam_obj = None
    threads = 1
    read_locations = {}
    ref_stats = {}
    ref_coverage = {}
    status = True
    error_msg = ''

    def __init__(self,input_file):
        '''

        :param input_file:
        '''
        self.alignment_file = input_file
        if not is_non_zero_file(input_file):
            self.status = False
            self.error_msg = "Error bam file {} does not exist".format(input_file)
            return
        index_file = "{}.bai".format(input_file)
        self.index_file = index_file
        if not is_non_zero_file(index_file):
            (stdout,stderr) =self.index_bam()
        if not is_non_zero_file(index_file):
            self.status = False
            self.error_msg = "STDOUT:{}\nSTDERR:{}".format(stdout,stderr)
            return
        self.ref_stats = self.get_bam_stats()
        self.init_base_cov()
        self.pysam_obj = pysam.AlignmentFile(input_file, "rb")
        self.process_bam()


    def init_base_cov(self):
        '''
        Uses the contig lengths from self.ref_stats to create a list of positions with counts initialized to 0
        :return:
        '''
        for contig_id in self.ref_stats:
            self.ref_coverage[contig_id] = [0] * self.ref_stats[contig_id]['length']


    def process_bam(self):
        '''
        Reads a bam file line by line and produces summary statistics based on each contig
        :return:
        '''
        for contig_id in self.ref_stats:
            contig_len = self.ref_stats[contig_id]['length']
            num_reads = 0
            total_bases = 0
            lengths = []
            qualities = []
            for read in self.pysam_obj.fetch(contig_id):
                num_reads+=1
                read_id = read.query_name
                seq = read.query_sequence
                length = len(seq)
                total_bases += length
                lengths.append(length)
                qual = read.query_qualities
                qscore = self.calc_mean_qscores(qual)
                qualities.append(qscore)
                self.ref_stats[contig_id]['reads'][read_id] = (length,qscore)
                if contig_id == '*':
                    continue
                start_pos = read.reference_start
                aln_len = read.query_alignment_length
                for i in range(start_pos,start_pos+aln_len):
                    if i < contig_len:
                        self.ref_coverage[contig_id][i]+=1

            lengths = sorted(lengths,reverse=True)
            if len(self.ref_coverage[contig_id]) > 0:
                self.ref_stats[contig_id]['mean_cov'] = statistics.mean(self.ref_coverage[contig_id])
                self.ref_stats[contig_id]['covered_bases'] = self.count_cov_bases(self.ref_coverage[contig_id])
            self.ref_stats[contig_id]['n50'] = self.calc_n50(lengths,total_bases)
            self.ref_stats[contig_id]['num_reads'] = num_reads
            if len(lengths) > 0:
                self.ref_stats[contig_id]['median_len'] = statistics.median(lengths)
                self.ref_stats[contig_id]['mean_len'] = statistics.mean(lengths)
            if len(qualities) > 0:
                self.ref_stats[contig_id]['median_qual'] = statistics.median(qualities)
                self.ref_stats[contig_id]['mean_qual'] = statistics.mean(qualities)
        return

    def calc_n50(self,lengths,total_length):
        '''
        Calculates the N50 of a set of read lengths
        :param lengths: list of ints
        :param total_length: int total number of bases accross all reads
        :return: int N50
        '''
        target_len = int(total_length / 2)
        s = 0
        global l
        for l in lengths:
            if s >= target_len:
                return l
            s+=l
        return l

    def count_cov_bases(self,list_of_values,min_value=1,max_value=9999999999999):
        '''
        Counts positions where the count is >=min and <= max
        :param list_of_values: list of ints
        :param min_value: int
        :param max_value: int
        :return: int number of positions meeting this threshold
        '''
        total = 0
        for v in list_of_values:
            if v >= min_value and v<=max_value:
                total+=1
        return total



    def calc_mean_qscores(self,qual):
        '''
        Calculates the mean quality score for a read where they have been converted to phred
        :param qual: string of phred 33 ints for quality
        :return: float mean qscore
        '''
        score = sum(qual)
        length = len(qual)
        if length == 0:
            return 0

        return score / length


    def get_bam_stats(self):
        '''
                Wrapper class around SAMTOOLS IDXSTATS for getting information about bam file
                :return:
                '''
        cmd = [
            'samtools',
            'idxstats',
            "{}".format(self.alignment_file)
        ]
        cmd = " ".join(cmd)
        (stdout,stderr) = run_command(cmd)
        result = {}
        stdout = stdout.split("\n")
        for row in stdout:
            row = row.split("\t")
            if len(row) < 4:
                continue
            result[row[0]] = {'length':int(row[1]),
                              'reads': {},'num_reads':0,'mean_cov':0,
                              'covered_bases':0,'mean_len':0,'median_len':0,
                              'mean_qual':0,'median_qual':0,'n50':0}
        return result


    def index_bam(self):
        '''
        Wrapper class around SAMTOOLS INDEX for creating a bam index file
        :return:
        '''
        cmd = [
            'samtools',
            'index',
            '-@',"{}".format(self.threads),
            '-o', "{}".format(self.index_file),
            "{}".format(self.alignment_file)
        ]
        cmd = " ".join(cmd)
        return run_command(cmd)