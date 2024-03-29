#!/usr/bin/env python
import argparse as ap
import os
import sys
from Sequenoscope.constant import SequenceTypes
from Sequenoscope.version import __version__
from Sequenoscope.utils.parser import GeneralSeqParser 
from Sequenoscope.utils.sequence_class import Sequence
from Sequenoscope.analyze.minimap2 import Minimap2Runner
from Sequenoscope.analyze.fastP import FastPRunner
from Sequenoscope.analyze.kat import KatRunner
from Sequenoscope.analyze.processing import SamBamProcessor
from Sequenoscope.analyze.fastq_extractor import FastqExtractor
from Sequenoscope.analyze.seq_manifest import SeqManifest
from Sequenoscope.utils.parser import FastqPairedEndRenamer
from Sequenoscope.analyze.seq_manifest import SeqManifestSummary

def parse_args():
    parser = ap.ArgumentParser(prog="sequenoscope",
                               usage="sequenoscope analyze --input_fastq <file.fq> --input_reference <ref.fasta> -o <out> -seq_type <sr>[options]\nFor help use: sequenoscope analyze -h or sequenoscope analyze --help", 
                                description="%(prog)s version {}: a tool for analyzing and processing sequencing data.".format(__version__), 
                                formatter_class= ap.RawTextHelpFormatter)

    parser._optionals.title = "Arguments"

    parser.add_argument("--input_fastq", metavar="", required=True, nargs="+", help="[REQUIRED] Path to fastq files to process.")
    parser.add_argument("--input_reference", metavar="", required=True, help="[REQUIRED] Path to reference database to process")
    parser.add_argument("-seq_sum", "--sequencing_summary", metavar="", help="Path to sequencing summary for manifest creation")
    parser.add_argument("-start", "--start_time", default=0, metavar="", help="Start time when no seq summary is provided")
    parser.add_argument("-end", "--end_time", default=100, metavar="", help="End time when no seq summary is provided")
    parser.add_argument("-o", "--output", metavar="", required=True, help="[REQUIRED] Output directory designation")
    parser.add_argument("-o_pre", "--output_prefix", metavar="", default= "sample", help="Output file prefix designation. default is [sample]")
    parser.add_argument("-seq_type", "--sequencing_type", required=True, metavar="", type= str, choices=['SE', 'PE'], help="A designation of the type of sequencing utilized for the input fastq files")
    parser.add_argument("-t", "--threads", default= 1, metavar="", type=int, help="A designation of the number of threads to use")
    parser.add_argument("-min_len", "--minimum_read_length", default= 15, metavar="", type=int, help="A designation of the minimum read length. reads shorter than the integer specified required will be discarded, default is 15")
    parser.add_argument("-max_len", "--maximum_read_length", default= 0, metavar="", type=int, help="A designation of the maximum read length. reads longer than the integer specified required will be discarded, default is 0 meaning no limitation")
    parser.add_argument("-trm_fr", "--trim_front_bp", default= 0, metavar="", type=int, help="A designation of the how many bases to trim from the front of the sequence, default is 0.")
    parser.add_argument("-trm_tail", "--trim_tail_bp", default= 0,metavar="", type=int, help="A designation of the how many bases to trim from the tail of the sequence, default is 0")
    #parser.add_argument('--exclude', required=False, help='Choose to exclude reads based on reference instead of including them', action='store_true')
    parser.add_argument('--kat_hist_kmer', default= 27, metavar="", type=int, help="A designation of the kmer size when running kat hist")
    parser.add_argument('--minimap2_kmer', default= 15, metavar="", type=int, help="A designation of the kmer size when running minimap2")
    parser.add_argument('--force', required=False, help='Force overwite of existing results directory', action='store_true')
    parser.add_argument('-v', '--version', action='version', version="%(prog)s " + __version__)
    return parser.parse_args()

def run():
    args = parse_args()
    input_fastq = args.input_fastq
    input_reference = args.input_reference
    seq_summary = args.sequencing_summary
    start_time = args.start_time
    end_time = args.end_time
    out_directory = args.output
    out_prefix = args.output_prefix
    seq_class= args.sequencing_type
    threads = args.threads
    kat_hist_kmer_size = args.kat_hist_kmer
    minimap_kmer_size = args.minimap2_kmer
    min_len = args.minimum_read_length
    max_len = args.maximum_read_length
    trim_front = args.trim_front_bp
    trim_tail = args.trim_tail_bp
    #exclude = args.exclude
    force = args.force

    print("-"*40)
    print(f"Sequenoscope analyze version {__version__}: processing and analyzing reads based on given paramters")
    print("-"*40)

    ## intializing directory for files

    if not os.path.isdir(out_directory):
        os.mkdir(out_directory, 0o755)
    elif not force:
        print(f"Error directory {out_directory} already exists, if you want to overwrite existing results then specify --force")
        sys.exit()

    ##checking fastq files

    #if seq_class == 'pe':
    if seq_class.upper() == SequenceTypes.paired_end:
        if not len(input_fastq) == 2:
            print("Error: Missing second paired-end sequencing file or additional files detected. Use 'SE' if utilizing single-end long-read sequencing files.")
            sys.exit()
    elif seq_class.upper() == SequenceTypes.single_end:
        if not len(input_fastq) == 1:
            print("Error: Multiple files detected for single-end long read sequencing. Use 'PE' for paired-end short-read sequencing files.")
            sys.exit()

    ## initiating sequence class object

    print("-"*40)
    print("Processing sequence fastq file...")
    print("-"*40)

    sequencing_sample = Sequence("Test", input_fastq)
    
    ## extracting reads into a read list

    extractor_run = FastqExtractor(sequencing_sample, out_prefix=f"{out_prefix}_read_list",
                                    out_dir=out_directory)
    if seq_class.upper() == SequenceTypes.paired_end:
        ## generate a read set for renaming read_ids
        extractor_run.extract_paired_reads()

        ##rename
        rename_read_ids_run = FastqPairedEndRenamer(sequencing_sample, extractor_run.result_files["read_list_file"], 
                                                    out_prefix=f"{out_prefix}_renamed_reads", out_dir=out_directory)
        rename_read_ids_run.rename()

        ##overwrite class objects with renamed files
        sequencing_sample = Sequence("Test", rename_read_ids_run.result_files["fastq_file_renamed"])
        extractor_run = FastqExtractor(sequencing_sample, out_prefix=f"{out_prefix}_read_list",
                                    out_dir=out_directory)
        
        ##extract read ids
        extractor_run.alt_extract_paired_reads()
    elif seq_class.upper() == SequenceTypes.single_end:
        extractor_run.extract_single_reads()

    ## filtering reads with fastp

    fastp_run_process = FastPRunner(sequencing_sample, out_directory, f"{out_prefix}_fastp_output", 
                                    min_read_len=min_len, max_read_len=max_len, trim_front_bp=trim_front,
                                    trim_tail_bp=trim_tail, report_only=False, dedup=False, threads=threads)

    
    fastp_run_process.run_fastp()

    ## mapping to reference via minimap2 and samtools

    print("-"*40)
    print("Mapping fastq based on the provided reference fasta file....")
    print("-"*40)

    sequencing_sample_filtered = Sequence("Test", fastp_run_process.result_files["output_files_fastp"])
    minimap_run_process = Minimap2Runner(sequencing_sample_filtered, out_directory, input_reference,
                                        f"{out_prefix}_mapped_sam", threads=threads,
                                        kmer_size=minimap_kmer_size)
    minimap_run_process.run_minimap2()

    sam_to_bam_process = SamBamProcessor(minimap_run_process.result_files["sam_output_file"], out_directory,
                                         input_reference, f"{out_prefix}_mapped_bam", thread=threads)
    sam_to_bam_process.run_samtools_bam()

    bam_to_fastq_process = SamBamProcessor(sam_to_bam_process.result_files["bam_output"], out_directory,
                                         input_reference, f"{out_prefix}_mapped_fastq", thread=threads)
    bam_to_fastq_process.run_samtools_fastq()

    print("-"*40)
    print("Analyzing kmers...")
    print("-"*40)

    # using kat hist to analyze kmers

    kat_run = KatRunner(sequencing_sample_filtered, input_reference, out_directory, f"{out_prefix}_kmer_analysis", kmersize = kat_hist_kmer_size)
    kat_run.kat_hist()

    print("-"*40)
    print("Creating manifest files...")
    print("-"*40)

    if seq_summary is not None:
        
        manifest_with_sum_run = SeqManifest(out_prefix,
                               sam_to_bam_process.result_files["bam_output"], 
                               f"{out_prefix}_manifest",
                               out_dir=out_directory,
                               fastp_fastq=fastp_run_process.result_files["output_files_fastp"],
                               read_list=extractor_run.result_files["read_list_file"],
                               in_seq_summary=seq_summary
                               )
        
        kmer_file = GeneralSeqParser(kat_run.result_files["hist"]["json_file"], "json")
        fastp_file = GeneralSeqParser(fastp_run_process.result_files["json"], "json")

        seq_summary_single_end_run = SeqManifestSummary(out_prefix,
                                manifest_with_sum_run.bam_obj, 
                                f"{out_prefix}_manifest_summary",
                                out_dir=out_directory,
                                kmer_json_file=kmer_file.parsed_file,
                                fastp_json_file=fastp_file.parsed_file
                                )
    
        seq_summary_single_end_run.generate_summary()

    else:
        
        manifest_no_sum_run = SeqManifest(out_prefix,
                               sam_to_bam_process.result_files["bam_output"], 
                               f"{out_prefix}_manifest",
                               out_dir=out_directory,
                               fastp_fastq=fastp_run_process.result_files["output_files_fastp"],
                               read_list=extractor_run.result_files["read_list_file"],
                               in_fastq=input_fastq,
                               start_time=start_time,
                               end_time=end_time
                               )
        
        kmer_file = GeneralSeqParser(kat_run.result_files["hist"]["json_file"], "json")
        fastp_file = GeneralSeqParser(fastp_run_process.result_files["json"], "json")

        if seq_class.upper() == SequenceTypes.paired_end:
            seq_summary_no_sum_run = SeqManifestSummary(out_prefix,
                                    manifest_no_sum_run.bam_obj, 
                                    f"{out_prefix}_manifest_summary",
                                    out_dir=out_directory,
                                    kmer_json_file=kmer_file.parsed_file,
                                    fastp_json_file=fastp_file.parsed_file,
                                    paired=True
                                    )
        
            
        else:
            seq_summary_no_sum_run = SeqManifestSummary(out_prefix,
                                    manifest_no_sum_run.bam_obj, 
                                    f"{out_prefix}_manifest_summary",
                                    out_dir=out_directory,
                                    kmer_json_file=kmer_file.parsed_file,
                                    fastp_json_file=fastp_file.parsed_file,
                                    paired=False
                                    )
        
        seq_summary_no_sum_run.generate_summary()
        


    print("-"*40)
    print("All Done!")
    print("-"*40)