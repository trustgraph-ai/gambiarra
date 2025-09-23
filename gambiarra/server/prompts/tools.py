"""
Tool descriptions for Gambiarra with comprehensive XML-based tool specifications.
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
- args: (required) Contains the write operation specification
  - file: (required) The file specification
    - path: (required) The path of the file to write to (relative to the current workspace directory)
  - content: (required) The content to write to the file. When performing a full rewrite of an existing file or creating a new one, ALWAYS provide the COMPLETE intended content of the file, without any truncation or omissions. You MUST include ALL parts of the file, even if they haven't been modified. Do NOT include the line numbers in the content though, just the actual content of the file.
  - line_count: (required) The number of lines in the file. Make sure to compute this based on the actual content of the file, not the number of lines in the content you're providing.

Usage:
<write_to_file>
<args>
<file>
<path>hello.py</path>
</file>
<content>#!/usr/bin/env python3

def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
</content>
<line_count>7</line_count>
</args>
</write_to_file>

## list_files
Description: List files and directories in a specified directory. This tool helps you understand the structure of the project and discover what files exist.
Parameters:
- args: (required) Contains the list operation specification
  - path: (required) The directory path to list (relative to the current workspace directory)
  - recursive: (optional) Whether to list files recursively. Use 'true' for recursive listing, 'false' for just the immediate directory. Defaults to false.

Usage:
<list_files>
<args>
<path>src</path>
<recursive>true</recursive>
</args>
</list_files>

## search_files
Description: Search for text patterns within files using regular expressions. This tool is useful for finding specific code patterns, function definitions, or text across multiple files.
Parameters:
- args: (required) Contains the search specification
  - path: (required) The directory path to search in (relative to the current workspace directory)
  - regex: (required) The regular expression pattern to search for
  - file_pattern: (optional) Glob pattern to filter which files to search (e.g., "*.py", "*.js")

Usage:
<search_files>
<args>
<path>src</path>
<regex>def.*main</regex>
<file_pattern>*.py</file_pattern>
</args>
</search_files>

## execute_command
Description: Execute a command in the terminal. This tool allows you to run CLI commands, compile code, run tests, install dependencies, and perform other system operations.
Parameters:
- args: (required) Contains the command specification
  - command: (required) The shell command to execute

Usage:
<execute_command>
<args>
<command>python -m pytest tests/</command>
</args>
</execute_command>

## search_and_replace
Description: Find and replace text in a file using literal text or regular expressions. This tool is useful for making targeted changes to existing files.
Parameters:
- args: (required) Contains the search and replace specification
  - path: (required) The file path (relative to the current workspace directory)
  - search: (required) The text or regex pattern to search for
  - replace: (required) The replacement text

Usage:
<search_and_replace>
<args>
<path>config.py</path>
<search>DEBUG = True</search>
<replace>DEBUG = False</replace>
</args>
</search_and_replace>

## insert_content
Description: Insert content at a specific line number in a file. Use line number 0 to append at the end of the file.
Parameters:
- args: (required) Contains the insert specification
  - path: (required) The file path (relative to the current workspace directory)
  - line_number: (required) The line number where to insert content (0 to append at end)
  - content: (required) The content to insert

Usage:
<insert_content>
<args>
<path>src/app.py</path>
<line_number>10</line_number>
<content># Added logging configuration
import logging
logging.basicConfig(level=logging.INFO)</content>
</args>
</insert_content>

## list_code_definition_names
Description: Get an overview of code definitions (functions, classes, etc.) in a source code file. This is useful for understanding the structure of a file before making changes.
Parameters:
- args: (required) Contains the file specification
  - path: (required) The file path (relative to the current workspace directory)

Usage:
<list_code_definition_names>
<args>
<path>src/utils.py</path>
</args>
</list_code_definition_names>

## attempt_completion
Description: After each tool use, the user will respond with the result of that tool use, i.e. if it succeeded or failed, along with any reasons for failure. Once you've received the results of tool uses and can confirm that the task is complete, use this tool to present the result of your work to the user. The user may respond with feedback if they are not satisfied with the result, which you can use to make improvements and try again.
IMPORTANT NOTE: This tool CANNOT be used until you've confirmed from the user that any previous tool uses were successful. Before using this tool, ensure all tasks are complete and tested.
Parameters:
- args: (required) Contains the completion specification
  - result: (required) The result of the task. Formulate this result in a way that is final and does not require further input from the user. Don't end your result with questions or offers for further assistance.

Usage:
<attempt_completion>
<args>
<result>Successfully created a Python hello world program in hello.py and verified it runs correctly.</result>
</args>
</attempt_completion>

## ask_followup_question
Description: Ask the user a follow-up question when you need clarification or additional information to complete the task. Use this when the task requirements are ambiguous or when you need to make important decisions that require user input.
Parameters:
- args: (required) Contains the question specification
  - question: (required) The question to ask the user

Usage:
<ask_followup_question>
<args>
<question>Would you like me to add error handling to the main function as well?</question>
</args>
</ask_followup_question>

## update_todo_list
Description: Create or update a todo list to track progress on complex tasks. Use markdown checkbox format. This helps you organize multi-step tasks and ensures nothing is forgotten.
Parameters:
- args: (required) Contains the todo list specification
  - todos: (required) The todo list in markdown format

Usage:
<update_todo_list>
<args>
<todos>
- [x] Create main.py file
- [x] Add hello world function
- [ ] Add error handling
- [ ] Write tests
</todos>
</args>
</update_todo_list>

## apply_diff
Description: Apply a unified diff patch to a file. Use this tool when you have a specific diff/patch that needs to be applied to modify a file. This is more efficient than search_and_replace for larger changes.
Parameters:
- args: (required) Contains the diff specification
  - path: (required) The file path to apply the diff to (relative to the current workspace directory)
  - diff: (required) The unified diff content to apply
  - start_line: (optional) The starting line number for context

Usage:
<apply_diff>
<args>
<path>src/config.py</path>
<diff>@@ -10,3 +10,5 @@
 DEBUG = False
 PORT = 8080
 HOST = 'localhost'
+# Added new configuration
+MAX_CONNECTIONS = 100
+TIMEOUT = 30</diff>
</args>
</apply_diff>

## multi_apply_diff
Description: Apply multiple diff patches to different files efficiently in a single operation. This is useful when you need to make coordinated changes across multiple files.
Parameters:
- args: (required) Contains the multi-diff specification
  - diffs: (required) Array of diff operations
    - path: (required) The file path for this diff
    - diff: (required) The unified diff content
    - start_line: (optional) The starting line number for context
  - continue_on_error: (optional) Whether to continue applying other diffs if one fails (default: false)

Usage:
<multi_apply_diff>
<args>
<diffs>
  <diff>
    <path>src/module1.py</path>
    <diff>@@ -5,2 +5,3 @@
 import os
+import sys
 import json</diff>
  </diff>
  <diff>
    <path>src/module2.py</path>
    <diff>@@ -10,2 +10,3 @@
 def process():
+    # Added processing logic
     pass</diff>
  </diff>
</diffs>
<continue_on_error>false</continue_on_error>
</args>
</multi_apply_diff>

## edit_file
Description: Use this tool to make intelligent edits to a file. This tool understands context and can make complex edits with minimal specification. You should specify only the lines you want to change, using special comments to represent unchanged code.
Parameters:
- args: (required) Contains the edit specification
  - path: (required) The target file to modify (full path relative to workspace)
  - old_str: (required) The exact string to replace
  - new_str: (required) The replacement string
  - occurrence: (optional) Which occurrence to replace (1-based, 0 for all)
  - context_lines: (optional) Number of context lines to show for verification (default: 3)

Usage:
<edit_file>
<args>
<path>src/app.py</path>
<old_str>def process_data(data):
    # Process the data
    return data</old_str>
<new_str>def process_data(data):
    # Validate input
    if not data:
        raise ValueError("Data cannot be empty")
    # Process the data
    return data.strip().lower()</new_str>
</args>
</edit_file>

## codebase_search
Description: Find files most relevant to the search query using semantic search. Searches based on meaning rather than exact text matches. By default searches entire workspace. Reuse the user's exact wording unless there's a clear reason not to - their phrasing often helps semantic search.
Parameters:
- args: (required) Contains the search specification
  - query: (required) The search query. Reuse the user's exact wording/question format unless there's a clear reason not to.
  - path: (optional) Limit search to specific subdirectory (relative to the current workspace directory). Leave empty for entire workspace.
  - file_types: (optional) File extensions to search (e.g., [".py", ".js"])
  - max_results: (optional) Maximum number of results to return (default: 20)
  - search_type: (optional) Type of search - "semantic", "text", "regex", or "auto" (default: "auto")

Usage:
<codebase_search>
<args>
<query>User login and password hashing</query>
<path>src/auth</path>
<file_types>[".py"]</file_types>
<max_results>10</max_results>
</args>
</codebase_search>

## new_task
Description: Create a new subtask or task workflow when you need to organize complex work into smaller, manageable pieces. This helps track dependencies and progress.
Parameters:
- args: (required) Contains the task specification
  - task_name: (required) Name/title of the new task
  - description: (required) Detailed description of what the task should accomplish
  - parent_task_id: (optional) ID of parent task if this is a subtask
  - priority: (optional) Priority level - "low", "medium", "high", or "critical" (default: "medium")

Usage:
<new_task>
<args>
<task_name>Implement user authentication</task_name>
<description>Add JWT-based authentication with login, logout, and token refresh endpoints</description>
<priority>high</priority>
</args>
</new_task>

## report_bug
Description: Report a bug or issue encountered during task execution. This helps track problems that need to be resolved.
Parameters:
- args: (required) Contains the bug report specification
  - title: (required) Brief title describing the bug
  - description: (required) Detailed description of the bug and how to reproduce it
  - severity: (optional) Severity level - "low", "medium", "high", or "critical" (default: "medium")
  - error_message: (optional) Error message if any
  - context: (optional) Additional context about when the bug occurred

Usage:
<report_bug>
<args>
<title>Database connection timeout</title>
<description>Connection to PostgreSQL database times out after 30 seconds when running migration scripts</description>
<severity>high</severity>
<error_message>psycopg2.OperationalError: connection timeout expired</error_message>
</args>
</report_bug>"""


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
        "update_todo_list",
        "apply_diff",
        "multi_apply_diff",
        "edit_file",
        "codebase_search",
        "new_task",
        "report_bug"
    ]