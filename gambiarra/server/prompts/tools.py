"""
Tool descriptions for Gambiarra with comprehensive XML-based tool specifications.
"""

from typing import List


def get_tool_descriptions() -> str:
    """Generate detailed tool descriptions with examples."""
    return """# Tools

**IMPORTANT XML FORMAT RULES:**
- Most tools use FLAT format: `<tool_name><param>value</param></tool_name>`
- Only these tools use NESTED format with `<args>`: `read_file`, `find_file`, `store_knowledge`, `retrieve_knowledge`, `create_plan`, `search_playbooks`, `execute_playbook`
- ALL editing/workflow tools use FLAT format: `write_to_file`, `search_and_replace`, `insert_content`, `list_code_definition_names`, `attempt_completion`, `ask_followup_question`, `update_todo_list`
- When in doubt, check the Usage example for the specific tool below

## read_file
Description: Read and view the contents of a file. This tool can handle text files, source code, configuration files, and more.
Parameters:
- args: (required) Contains the file specification
  - path: (required) The file path relative to the current workspace directory

Usage:
<read_file>
<args>
<path>src/main.py</path>
</args>
</read_file>

## write_to_file
Description: Write content to a file. Use this tool ONLY for:
1. **Creating NEW files** that don't exist yet
2. **Complete rewrites** where you intentionally want to replace the ENTIRE file contents

IMPORTANT: This tool OVERWRITES the entire file. For making targeted edits to existing files, use search_and_replace instead. If the file doesn't exist, it will be created along with any necessary directories.
Parameters:
- path: (required) The path of the file to write to (relative to the current workspace directory)
- content: (required) The content to write to the file. When performing a full rewrite of an existing file or creating a new one, ALWAYS provide the COMPLETE intended content of the file, without any truncation or omissions. You MUST include ALL parts of the file, even if they haven't been modified.
- line_count: (required) The number of lines in the file. Count the actual newlines in your content.

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

## find_file
Description: Search for files by name pattern within a directory. Much faster than using list_files repeatedly. Use this when you need to find a specific file (like README, package.json, etc.) without knowing its exact location. Supports glob patterns like "README*", "*.json", "test_*.py".
Parameters:
- args: (required) Contains the search specification
  - path: (required) The directory to search in (relative to workspace)
  - pattern: (required) Glob pattern to match filenames (e.g., "README*", "*.md", "vite.config.*")
  - max_depth: (optional) Maximum directory depth to search (default: 3)

Usage:
<find_file>
<args>
<path>node_modules/@trustgraph/react-state</path>
<pattern>README*</pattern>
</args>
</find_file>

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
- timeout: (optional) Maximum time in seconds to wait for command completion. Defaults to 30 seconds if not specified. Set appropriately based on operation type:
  * Quick commands (ls, cat): 5-10 seconds
  * Package installs (npm install): 300 seconds
  * Build operations (npm run build): 180 seconds
  * Test suites: 120-180 seconds

Usage:
<execute_command>
<command>npm install --yes</command>
<timeout>300</timeout>
</execute_command>

## search_and_replace
Description: **PRIMARY EDITING TOOL** - Use this for making targeted changes to existing files. Finds exact text matches and replaces them. This is the recommended way to edit files because it's precise, safe, and doesn't risk corrupting the file.

When to use:
- Modifying existing code or configuration
- Updating function implementations
- Changing values or settings
- Any edit to an existing file (unless you need a complete rewrite)

IMPORTANT: Use exact parameter names: `path`, `search`, `replace` (NOT file, search_string, replacement, etc.)

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
Description: Insert new lines at a specific position in a file. Use this when you need to add content without replacing anything.

When to use:
- Adding new imports at the top of a file
- Adding new functions or classes
- Inserting configuration entries
- Appending to end of file (use line_number 0)
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
Description: After each tool use, the user will respond with the result of that tool use, i.e. if it succeeded or failed, along with any reasons for failure. Once you've received the results of tool uses and can confirm that the task is complete, use this tool to present the result of your work to the user. The user may respond with feedback if they are not satisfied with the result, which you can use to make improvements and try again.
IMPORTANT NOTE: This tool CANNOT be used until you've confirmed from the user that any previous tool uses were successful. Before using this tool, ensure all tasks are complete and tested.
Parameters:
- result: (required) The result of the task. Formulate this result in a way that is final and does not require further input from the user. Don't end your result with questions or offers for further assistance.

Usage:
<attempt_completion>
<result>Successfully created a Python hello world program in hello.py and verified it runs correctly.</result>
</attempt_completion>

## ask_followup_question
Description: Ask the user a follow-up question when you need clarification or additional information to complete the task. Use this when the task requirements are ambiguous or when you need to make important decisions that require user input.
Parameters:
- question: (required) The question to ask the user

Usage:
<ask_followup_question>
<question>Would you like me to add error handling to the main function as well?</question>
</ask_followup_question>

## update_todo_list
Description: Create or update a todo list to track progress on complex tasks. Use markdown checkbox format. This helps you organize multi-step tasks and ensures nothing is forgotten.
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
</update_todo_list>

## list_knowledge
Description: List all knowledge that has been automatically extracted and stored during this session. When you read README files, package.json, or other important files, the server automatically extracts key information (like configuration, dependencies, API endpoints) and stores it. Use this tool to see what knowledge is available before asking followup questions or claiming information is missing.
Parameters: None

Usage:
<list_knowledge></list_knowledge>

## search_playbooks
Description: Search the playbook catalog for proven, tested command sequences. Playbooks are pre-tested workflows for common operations like creating projects, installing dependencies, or running builds. ALWAYS search playbooks before improvising complex multi-step operations.
Parameters:
- args: (required) Contains the search specification
  - query: (required) Natural language description of what you want to do (e.g., "create react app", "install package", "run build")

Usage:
<search_playbooks>
<args>
<query>create a react app with typescript</query>
</args>
</search_playbooks>

## execute_playbook
Description: Execute a playbook - a pre-tested sequence of commands guaranteed to work in this environment. Use this after searching playbooks to run the selected playbook. Playbooks handle timeouts, non-interactive prompts, and working directories correctly.
Parameters:
- args: (required) Contains the execution specification
  - name: (required) Name of the playbook to execute (from search results)
  - variables: (optional) Variables to substitute in commands as JSON object (e.g., {"app_name": "my-app", "package_name": "react"})

Usage:
<execute_playbook>
<args>
<name>create-react-vite-typescript</name>
<variables>{"app_name": "my-react-app"}</variables>
</args>
</execute_playbook>

## store_knowledge
Description: Store information in memory for retrieval in later steps. Use this to save important information extracted from documentation, configuration details, or intermediate results that will be needed later. This is CRITICAL for multi-step workflows where information from one step must be available in subsequent steps.
Parameters:
- args: (required) Contains the storage specification
  - key: (required) A descriptive key to identify this information (e.g., "vite-proxy-config", "api-endpoint", "database-schema")
  - value: (required) The information to store (can be text, JSON, code snippets, etc.)
  - description: (optional) Brief description of what this information is for

Usage:
<store_knowledge>
<args>
<key>vite-proxy-config</key>
<value>server: {
  proxy: {
    '/tg-sse': {
      target: 'ws://localhost:8088',
      ws: true
    }
  }
}</value>
<description>Vite proxy configuration for TrustGraph websocket from README</description>
</args>
</store_knowledge>

## retrieve_knowledge
Description: Retrieve information previously stored in memory. Use this to access information from earlier steps in a multi-step workflow. This ensures you have all necessary context even if earlier messages have been truncated from the conversation.
Parameters:
- args: (required) Contains the retrieval specification
  - key: (required) The key of the information to retrieve

Usage:
<retrieve_knowledge>
<args>
<key>vite-proxy-config</key>
</args>
</retrieve_knowledge>

## create_plan
Description: Create a structured plan for complex multi-step tasks. Use this at the START of any workflow with multiple steps to decompose the task into clear goals. Planning helps you stay organized, track progress, and ensure you don't forget important steps. The plan is stored in memory and can guide your work.
Parameters:
- args: (required) Contains the plan specification
  - task: (required) Brief description of the overall task
  - goals: (required) List of specific goals/steps to accomplish the task, in order
  - rationale: (optional) Brief explanation of the approach

Usage:
<create_plan>
<args>
<task>Set up React app with TrustGraph integration</task>
<goals>
1. Create React + TypeScript app with Vite
2. Downgrade to React 18 for compatibility
3. Install @trustgraph/react-state package
4. Read README to learn proxy configuration
5. Apply proxy config to vite.config.ts
6. Build chat interface with message history
7. Run build and fix any issues
</goals>
<rationale>Breaking down the setup into discrete steps ensures each dependency is handled in order and configurations are properly applied</rationale>
</args>
</create_plan>

"""


def get_available_tools() -> List[str]:
    """Get list of available tool names."""
    return [
        "read_file",
        "write_to_file",
        "list_files",
        "find_file",
        "search_files",
        "execute_command",
        "search_and_replace",
        "insert_content",
        "list_code_definition_names",
        "attempt_completion",
        "ask_followup_question",
        "update_todo_list",
        "search_playbooks",
        "execute_playbook",
        "store_knowledge",
        "retrieve_knowledge",
        "list_knowledge",
        "create_plan"
    ]
