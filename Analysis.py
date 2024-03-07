import pandas as pd
import re
import os
import sys

# ErrorLog->csv conversion motivarted from https://github.com/realtime/python-tools/tree/master


def match_step(line):
    """
    Check if line matches the pattern of "step".

    :param line: The line that the pattern is compared to.

    :return: First occurrence of the "step" pattern.
    """
    return re.match(r'\.step (.*)', line)

def match_fourier_header(line):
    """
    Check if line matches the pattern of "fourier_header".

    :param line: The line that the pattern is compared to.

    :return: First occurrence of the "fourier_header" pattern.
    """
    return re.match(r'Harmonic\s+Frequency\s+Fourier\s+Normalized\s+Phase\s+Normalized', line)

def match_fourier_data(line):
    """
    Check if line matches the pattern of "fourier_data".

    :param line: The line that the pattern is compared to.

    :return: First occurrence of the "fourier_data" pattern.
    """
    pattern = r'^\s*\d+\s+-?\d+\.\d+e[+-]\d+\s+-?\d+\.\d+e[+-]\d+\s+-?\d+\.\d+e[+-]\d+\s+-?\d+\.\d+(?:°|�)\s+-?\d+\.\d+(?:°|�)\s*$'
    return re.match(pattern, line)

def search_var(line):
    """
    Check if line matches the pattern of "variable_name".

    :param line: The line that the pattern is compared to.

    :return: First occurrence of the "variable_name" pattern.
    """
    return re.compile(r'(\S+)=(\S+)').search(line)

def log_to_csv(logfilename):
    """
    Convert the Error Log of LTspice into an csv storing information about the steps and spectral analysis for each step.

    :param logfilename: The name of the LTspice Error Log.

    :return: 1) Name of the variable modified in step. 2) Name of the csv file creatd.
    """
    # configurationsetup
    csvfilename = os.path.splitext(logfilename)[0] + '.csv'
    logfile = open(logfilename,'r')
    step = 0
    data = []
    var = ""

    # find first .step definition
    for line in logfile:    
        match = match_step(line)
        if match:
            var_match = search_var(line)
            if (var_match):
                var = var_match.group(1)
            break

    # iterate through all steps with parameters
    while match:
        step += 1
        # step line convert to { step }
        row = { 'step': int(step) }

        parameters = match.group(1).split()
        for p in parameters:
            [key, value] = p.split('=')
            row[key] = float(value)
        
        data.append(row)

        match = match_step(next(logfile))

    # iterate through rest of the file
    for line in logfile: 
        match = match_step(line)
        # address case with having multiple steps in Error Log
        if (match):
            step += 1
            # step line convert to { step }
            row = { 'step': int(step) }

            parameters = match.group(1).split()
            for p in parameters:
                [key, value] = p.split('=')
                row[key] = float(value)
            
            data.append(row)
        # Load data for spectral analysis for each step
        elif match_fourier_header(line):
            next(logfile)
            while True:
                line = next(logfile)
                match_fourier = match_fourier_data(line)
                if (match_fourier):
                    # fourier_data line convert to { step, Harmonic, Freq., FFT weight, normalized FFT weight, phase, normalized phase }
                    harmonic, frequency, fourier_component, normalized_component, phase, normalized_phase = match_fourier.group().split()
                    row = {'step': step, 'Harmonic': int(harmonic), 'Frequency': float(frequency),
                        'Fourier_Component': float(fourier_component), 'Normalized_Component': float(normalized_component),
                        'Phase': float(phase[:-1]), 'Normalized_Phase': float(normalized_phase[:-1])}  # Removing the '�' symbol
                    data.append(row)
                else:
                    break

    logfile.close()

    # convert the list "data" to csv file
    frame = pd.DataFrame(data).set_index('step')
    frame.to_csv(csvfilename)

    return var, csvfilename

def find_local_maxima(frequencies, amplitudes, threshold):
    """
    Find the local maxima of the frequencies vs amplitudes relationship while taking care of noise.

    :param frequencies: A list storing all frequencies.
    :param amplitudes: A list storing all amplituds.
    :param threshold: The minimum difference between two neighboring frequencies to be considered useful data.

    :return: 1) Indices of all local maximum. 2) Data point of the local maximum.
    """
    local_maxima = []
    local_maxima_indices = []

    # maxima recognized when greater than both previous and following data point by more than the value of threshold.
    for i in range(1, len(amplitudes) - 1):
        if amplitudes[i] > amplitudes[i - 1] and amplitudes[i] > amplitudes[i + 1]:
            if amplitudes[i] - amplitudes[i - 1] > threshold and amplitudes[i] - amplitudes[i + 1] > threshold:
                local_maxima.append((frequencies[i], amplitudes[i]))
                local_maxima_indices.append(i)
    return local_maxima_indices, local_maxima

def frequency_analysis(logfilename, var):
    """
    Analyze a csv file to retrieve first and second peak frequencies.

    :param logfilename: Name of the csv file.
    :param var: Variable that is changed in the LTspice simulation.

    :return: Result of the frequency analysis, storing information about steps and maximum frequencies.
    """
    data = pd.read_csv(logfilename)
    grouped_data = data.groupby('step')

    output = []
    threshold = 0.01

    # Find maximum for each step and append to output
    for step, group in grouped_data:
        step = group.values[0][:2]
        frequencies = group['Frequency'].values[1:]
        amplitudes = group['Normalized_Component'].values[1:]
        local_maxima_indices, local_maxima = find_local_maxima(frequencies, amplitudes, threshold) 
        # output format : { step, variable_name, maximum, maximum indices }
        row = { 'step': int(step[0]), var: step[1], 'maximum': local_maxima, 'maximum indices': local_maxima_indices }
        output.append(row)

    return output

def frequency_to_csv(values, var):
    """
    Convert a list of dat points to csv file.
    
    :param values: List of data points.
    :param var: Variable that is changed in the LTspice simulation.
    """
    csvfilename = '../data/' + var + '_resonance' + '.csv'
    data = []
    
    # Append the first two peak frequencies to output (if number of peaks >= 2)
    for step in values:
        if len(step['maximum']) < 2:
            continue
        row = { var: step[var], 'primary_freq': step['maximum'][0][0], 'secondary_freq': step['maximum'][1][0] }
        data.append(row)

    # write output csv file
    frame = pd.DataFrame(data).set_index(var)
    frame.to_csv(csvfilename)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print()
        print("Missing Argument (Require: python Analysis.py <logfilename>).")
        print("For example: Analysis.py ../data/Nanowire Resonator.log")
        print()
        sys.exit(1)

    logfilename = sys.argv[1]
    var, csvfilename = log_to_csv(logfilename)
    values = frequency_analysis(csvfilename, var)
    frequency_to_csv(values, var)
    print("\nAll done!!!\n")

