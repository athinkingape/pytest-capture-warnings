## pytest capture Warnings

This is a pytest plugin to collect and print a summary of all the warnings encountered during test execution and save them in a file.


# Installation

    pip install pytest-capture-warnings

# Usage 

    pytest --output <output_file> <file_to_test>
    or
    CAPTURE_WARNINGS_OUTPUT=<output_file> pytest <files_to_test>


# Flake8 Format
    
The output file is formatted on a flake8 format
    
    <filename/path>:<line number>:<character number>:<warning message>
