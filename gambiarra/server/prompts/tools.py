"""
Tool descriptions for Gambiarra - based on KiloCode's detailed tool prompts.
"""

from typing import List


def get_tool_descriptions() -> str:
    """Generate detailed tool descriptions with examples."""
    return """# Tools

## read_file
Description: Read and view the contents of a file. This tool can handle text files, source code, configuration files, and more.
Parameters:
- args: (required) Contains the file specification
  - file: (required) The file to read
    - path: (required) The file path relative to the current workspace directory

Usage:
<read_file>
<args>
<file>
<path>src/main.py</path>
</file>
</args>
</read_file>

## write_to_file
Description: Request to write content to a file. This tool is primarily used for **creating new files** or for scenarios where a **complete rewrite of an existing file is intentionally required**. If the file exists, it will be overwritten. If it doesn't exist, it will be created. This tool will automatically create any directories needed to write the file.
Parameters:
- path: (required) The path of the file to write to (relative to the current workspace directory)
- content: (required) The content to write to the file. When performing a full rewrite of an existing file or creating a new one, ALWAYS provide the COMPLETE intended content of the file, without any truncation or omissions. You MUST include ALL parts of the file, even if they haven't been modified. Do NOT include the line numbers in the content though, just the actual content of the file.
- line_count: (required) The number of lines in the file. Make sure to compute this based on the actual content of the file, not the number of lines in the content you're providing.

Usage:
<write_to_file>
<path>hello.py</path>
<content>#!/usr/bin/env python3

def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
</content>
<line_count>7</line_count>
</write_to_file>

## list_files
Description: List files and directories in a specified directory. This tool helps you understand the structure of the project and discover what files exist.
Parameters:
- path: (required) The directory path to list (relative to the current workspace directory)
- recursive: (optional) Whether to list files recursively. Use 'true' for recursive listing, 'false' for just the immediate directory. Defaults to false.

Usage:
<list_files>
<path>src</path>
<recursive>true</recursive>
</list_files>

## search_files
Description: Search for text patterns within files using regular expressions. This tool is useful for finding specific code patterns, function definitions, or text across multiple files.
Parameters:
- path: (required) The directory path to search in (relative to the current workspace directory)
- regex: (required) The regular expression pattern to search for
- file_pattern: (optional) Glob pattern to filter which files to search (e.g., "*.py", "*.js")

Usage:
<search_files>
<path>src</path>
<regex>def.*main</regex>
<file_pattern>*.py</file_pattern>
</search_files>

## execute_command
Description: Execute a command in the terminal. This tool allows you to run CLI commands, compile code, run tests, install dependencies, and perform other system operations.
Parameters:
- command: (required) The shell command to execute

Usage:
<execute_command>
<command>python -m pytest tests/</command>
</execute_command>

## search_and_replace
Description: Find and replace text in a file using literal text or regular expressions. This tool is useful for making targeted changes to existing files.
Parameters:
- path: (required) The file path (relative to the current workspace directory)
- search: (required) The text or regex pattern to search for
- replace: (required) The replacement text

Usage:
<search_and_replace>
<path>config.py</path>
<search>DEBUG = True</search>
<replace>DEBUG = False</replace>
</search_and_replace>

## insert_content
Description: Insert content at a specific line number in a file. Use line number 0 to append at the end of the file.
Parameters:
- path: (required) The file path (relative to the current workspace directory)
- line_number: (required) The line number where to insert content (0 to append at end)
- content: (required) The content to insert

Usage:
<insert_content>
<path>src/app.py</path>
<line_number>10</line_number>
<content># Added logging configuration
import logging
logging.basicConfig(level=logging.INFO)</content>
</insert_content>

## list_code_definition_names
Description: Get an overview of code definitions (functions, classes, etc.) in a source code file. This is useful for understanding the structure of a file before making changes.
Parameters:
- path: (required) The file path (relative to the current workspace directory)

Usage:
<list_code_definition_names>
<path>src/utils.py</path>
</list_code_definition_names>

## attempt_completion
Description: Signal that you have completed the user's task. Use this tool when you have successfully accomplished what the user asked for.
Parameters:
- result: (required) A description of what was accomplished

Usage:
<attempt_completion>
<result>Successfully created a Python hello world program in hello.py and verified it runs correctly.</result>
</attempt_completion>

## ask_followup_question
Description: Ask the user a follow-up question when you need clarification or additional information to complete the task.
Parameters:
- question: (required) The question to ask the user

Usage:
<ask_followup_question>
<question>Would you like me to add error handling to the main function as well?</question>
</ask_followup_question>

## update_todo_list
Description: Create or update a todo list to track progress on complex tasks. Use markdown checkbox format.
Parameters:
- todos: (required) The todo list in markdown format

Usage:
<update_todo_list>
<todos>
- [x] Create main.py file
- [x] Add hello world function
- [ ] Add error handling
- [ ] Write tests
</todos>
</update_todo_list>"""


def get_available_tools() -> List[str]:
    """Get list of available tool names."""
    return [
        "read_file",
        "write_to_file",
        "list_files",
        "search_files",
        "execute_command",
        "search_and_replace",
        "insert_content",
        "list_code_definition_names",
        "attempt_completion",
        "ask_followup_question",
        "update_todo_list"
    ]