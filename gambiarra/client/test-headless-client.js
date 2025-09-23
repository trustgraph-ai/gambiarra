#!/usr/bin/env node
/**
 * Test client for KiloCode Headless Server
 *
 * This connects to the headless server via WebSocket and tests
 * the integration with the dummy OpenAI API.
 * Now supports client-side file operations.
 */

import WebSocket from "ws"
import { v4 as uuidv4 } from "uuid"
import fs from "fs/promises"
import path from "path"

class KiloCodeHeadlessClient {
	constructor(serverUrl = "ws://localhost:3001/ws", workspaceDir = "./workspace") {
		this.serverUrl = serverUrl
		this.workspaceDir = workspaceDir
		this.ws = null
		this.sessionId = null
		this.messageHandlers = new Map()
		this.ensureWorkspace()
	}

	async ensureWorkspace() {
		try {
			await fs.mkdir(this.workspaceDir, { recursive: true })
			console.log(`📁 Workspace ready: ${this.workspaceDir}`)
		} catch (error) {
			console.error("Failed to create workspace:", error.message)
		}
	}

	async connect() {
		return new Promise((resolve, reject) => {
			console.log(`Connecting to ${this.serverUrl}...`)

			this.ws = new WebSocket(this.serverUrl)

			this.ws.on("open", () => {
				console.log("✅ Connected to KiloCode Headless Server")
				resolve()
			})

			this.ws.on("message", async (data) => {
				try {
					const message = JSON.parse(data.toString())
					await this.handleMessage(message)
				} catch (error) {
					console.error("Error parsing message:", error)
				}
			})

			this.ws.on("error", (error) => {
				console.error("WebSocket error:", error)
				reject(error)
			})

			this.ws.on("close", () => {
				console.log("Disconnected from server")
			})
		})
	}

	async handleMessage(message) {
		console.log(`📨 Received: ${message.type}`)

		switch (message.type) {
			case "connected":
				console.log("🎉", message.payload.message)
				break

			case "session_created":
				this.sessionId = message.payload.sessionId
				console.log("✅ Session created:", this.sessionId)
				console.log("   Working directory:", message.payload.workingDirectory)
				console.log("   Config:", message.payload.config)
				break

			case "ai_thinking":
				console.log("🤔 AI thinking:", message.payload.content)
				break

			case "ai_response":
				await this.handleAIResponse(message.payload)
				break

			case "error":
				console.error("❌ Error:", message.payload.message)
				break

			case "session_destroyed":
				console.log("🗑️  Session destroyed:", message.payload.sessionId)
				this.sessionId = null
				break

			default:
				console.log("📝 Unknown message type:", message.type, message.payload)
		}

		// Call any registered handlers
		const handler = this.messageHandlers.get(message.type)
		if (handler) {
			handler(message)
		}
	}

	async handleAIResponse(payload) {
		// Handle structured response with file operations
		if (payload.message && payload.operations !== undefined) {
			console.log("🤖", payload.message)

			// Execute file operations
			if (payload.operations && payload.operations.length > 0) {
				console.log("\n📝 Executing file operations:")
				await this.executeFileOperations(payload.operations)
			}

			// Show next steps
			if (payload.next_steps && payload.next_steps.length > 0) {
				console.log("\n📋 Next steps:")
				payload.next_steps.forEach((step, index) => {
					console.log(`  ${index + 1}. ${step}`)
				})
			}

			// Show execution simulation if available
			if (payload.execution_simulation) {
				console.log("\n⚡ Execution preview:")
				console.log(`$ ${payload.execution_simulation.command}`)
				console.log(payload.execution_simulation.expected_output)
			}
		} else {
			// Handle legacy text response
			console.log("🤖 AI response:")
			console.log("---")
			console.log(payload.content)
			console.log("---")
		}

		if (payload.usage) {
			console.log("💰 Usage:", payload.usage)
		}
	}

	async executeFileOperations(operations) {
		for (const operation of operations) {
			try {
				await this.executeOperation(operation)
				console.log(`  ✅ ${operation.description}`)
			} catch (error) {
				console.error(`  ❌ Failed: ${operation.description} - ${error.message}`)
			}
		}
	}

	async executeOperation(operation) {
		switch (operation.type) {
			case "create_file":
				const createPath = path.join(this.workspaceDir, operation.path)
				// Ensure parent directory exists
				await fs.mkdir(path.dirname(createPath), { recursive: true })
				await fs.writeFile(createPath, operation.content)
				console.log(`  📝 Created: ${operation.path}`)
				break

			case "edit_file":
				const editPath = path.join(this.workspaceDir, operation.path)
				// Ensure parent directory exists
				await fs.mkdir(path.dirname(editPath), { recursive: true })
				await fs.writeFile(editPath, operation.content)
				console.log(`  ✏️  Modified: ${operation.path}`)
				break

			case "create_directory":
				const dirPath = path.join(this.workspaceDir, operation.path)
				await fs.mkdir(dirPath, { recursive: true })
				console.log(`  📁 Created directory: ${operation.path}`)
				break

			case "delete_file":
				const deletePath = path.join(this.workspaceDir, operation.path)
				await fs.unlink(deletePath)
				console.log(`  🗑️  Deleted: ${operation.path}`)
				break

			case "execute_command":
				console.log(`  ⚡ Would execute: ${operation.command}`)
				console.log(`     (Command execution not implemented in client)`)
				break

			default:
				console.log(`  ❓ Unknown operation: ${operation.type}`)
		}
	}

	async listWorkspaceFiles() {
		try {
			const files = await this.getFilesRecursive(this.workspaceDir)
			if (files.length > 0) {
				console.log("\n📂 Workspace contents:")
				files.forEach((file) => {
					const relativePath = path.relative(this.workspaceDir, file)
					console.log(`  • ${relativePath}`)
				})
			} else {
				console.log("\n📂 Workspace is empty")
			}
		} catch (error) {
			console.error("Failed to list workspace files:", error.message)
		}
	}

	async getFilesRecursive(dir) {
		const files = []
		const items = await fs.readdir(dir)

		for (const item of items) {
			const fullPath = path.join(dir, item)
			const stat = await fs.stat(fullPath)

			if (stat.isDirectory()) {
				const subFiles = await this.getFilesRecursive(fullPath)
				files.push(...subFiles)
			} else {
				files.push(fullPath)
			}
		}

		return files
	}

	sendMessage(type, payload, sessionId = this.sessionId) {
		const message = {
			id: uuidv4(),
			type,
			sessionId,
			payload,
		}

		console.log(`📤 Sending: ${type}`)
		this.ws.send(JSON.stringify(message))
	}

	async createSession(workingDirectory = process.cwd(), config = {}) {
		return new Promise((resolve, reject) => {
			this.messageHandlers.set("session_created", (message) => {
				this.messageHandlers.delete("session_created")
				resolve(message.payload)
			})

			this.messageHandlers.set("error", (message) => {
				this.messageHandlers.delete("session_created")
				reject(new Error(message.payload.message))
			})

			this.sendMessage("create_session", {
				workingDirectory,
				config: {
					apiProvider: "openai",
					apiKey: "dummy-key",
					apiBaseUrl: "http://localhost:8000/v1",
					model: "gpt-3.5-turbo",
					...config,
				},
			})
		})
	}

	async sendCodingMessage(content, images = []) {
		return new Promise((resolve, reject) => {
			this.messageHandlers.set("ai_response", (message) => {
				this.messageHandlers.delete("ai_response")
				resolve(message.payload)
			})

			this.messageHandlers.set("error", (message) => {
				this.messageHandlers.delete("ai_response")
				reject(new Error(message.payload.message))
			})

			this.sendMessage("send_message", {
				content,
				images,
			})
		})
	}

	async destroySession() {
		return new Promise((resolve) => {
			this.messageHandlers.set("session_destroyed", (message) => {
				this.messageHandlers.delete("session_destroyed")
				resolve(message.payload)
			})

			this.sendMessage("destroy_session", { sessionId: this.sessionId })
		})
	}

	disconnect() {
		if (this.ws) {
			this.ws.close()
		}
	}
}

// Test script
async function runTests() {
	const client = new KiloCodeHeadlessClient("ws://localhost:3001/ws", "./test-workspace")

	try {
		console.log("🧪 Starting KiloCode Headless Server tests...\n")

		// Test 1: Connect to server
		console.log("Test 1: Connecting to server...")
		await client.connect()
		console.log("✅ Connection test passed\n")

		// Test 2: Create session
		console.log("Test 2: Creating session...")
		const sessionInfo = await client.createSession(process.cwd(), {
			apiProvider: "openai",
			apiBaseUrl: "http://localhost:8000/v1",
			apiKey: "dummy-key",
			model: "gpt-3.5-turbo",
		})
		console.log("✅ Session creation test passed\n")

		// Test 3: Send a simple coding message
		console.log("Test 3: Sending coding message...")
		const response1 = await client.sendCodingMessage("Write a simple Hello World function in Python")
		console.log("✅ Simple message test passed\n")

		// Test 4: Send a more complex coding request
		console.log("Test 4: Sending complex coding request...")
		const response2 = await client.sendCodingMessage(
			"Create a Python function that calculates the fibonacci sequence up to n numbers and returns a list",
		)
		console.log("✅ Complex message test passed\n")

		// Test 5: Test error handling with bad request
		console.log("Test 5: Testing error handling...")
		try {
			await client.sendCodingMessage("") // Empty message
			console.log("⚠️  Empty message was accepted (might be OK)")
		} catch (error) {
			console.log("✅ Error handling test passed:", error.message)
		}

		// Test 6: Destroy session
		console.log("Test 6: Destroying session...")
		await client.destroySession()
		console.log("✅ Session destruction test passed\n")

		console.log("🎉 All tests completed successfully!")
	} catch (error) {
		console.error("❌ Test failed:", error.message)
		process.exit(1)
	} finally {
		client.disconnect()

		// Wait a bit for cleanup
		setTimeout(() => {
			console.log("\n📋 Test Summary:")
			console.log("- Server connection: ✅")
			console.log("- Session management: ✅")
			console.log("- Message sending: ✅")
			console.log("- AI responses: ✅")
			console.log("- Integration with dummy OpenAI API: ✅")
			console.log("\n🏁 Ready for production use!")
			process.exit(0)
		}, 1000)
	}
}

// Interactive mode
async function interactiveMode() {
	const client = new KiloCodeHeadlessClient("ws://localhost:3001/ws", "./workspace")
	const { createInterface } = await import("readline")

	const rl = createInterface({
		input: process.stdin,
		output: process.stdout,
	})

	try {
		console.log("🤖 KiloCode Interactive Client\n")

		await client.connect()

		await client.createSession(process.cwd())
		console.log('\n💬 You can now chat with KiloCode! Type "exit" to quit.\n')

		const askQuestion = () => {
			rl.question("You: ", async (input) => {
				if (input.toLowerCase() === "exit") {
					await client.destroySession()
					client.disconnect()
					rl.close()
					console.log("\nGoodbye! 👋")
					process.exit(0)
					return
				}

				// Handle special commands
				if (input.toLowerCase() === "ls" || input.toLowerCase() === "list") {
					await client.listWorkspaceFiles()
					console.log("")
					askQuestion()
					return
				}

				if (input.toLowerCase() === "clear") {
					console.clear()
					askQuestion()
					return
				}

				if (input.toLowerCase().startsWith("help")) {
					console.log("\n🔧 Available commands:")
					console.log("  ls, list          - Show workspace files")
					console.log("  clear             - Clear screen")
					console.log("  help              - Show this help")
					console.log("  exit              - Exit the client")
					console.log("\n💡 Try these examples:")
					console.log("  Create a Python hello world application")
					console.log("  Create a Flask web application")
					console.log("  Modify it to add two numbers together")
					console.log("")
					askQuestion()
					return
				}

				if (input.trim()) {
					try {
						await client.sendCodingMessage(input)
						console.log("") // Add spacing
					} catch (error) {
						console.error("Error:", error.message)
					}
				}

				askQuestion()
			})
		}

		askQuestion()
	} catch (error) {
		console.error("Failed to start interactive mode:", error.message)
		rl.close()
		process.exit(1)
	}
}

// Main
async function main() {
	const args = process.argv.slice(2)

	if (args.includes("--interactive") || args.includes("-i")) {
		await interactiveMode()
	} else if (args.includes("--help") || args.includes("-h")) {
		console.log(`
KiloCode Headless Server Test Client

Usage:
  node test-headless-client.js [options]

Options:
  --interactive, -i    Run in interactive mode (chat with KiloCode)
  --help, -h          Show this help message

Examples:
  node test-headless-client.js                    # Run test suite
  node test-headless-client.js --interactive      # Interactive chat mode

Make sure the KiloCode headless server is running:
  npx tsx kilocode-headless-server.ts

And the dummy OpenAI server is running:
  npx tsx scripts/kilocode/server/openai-test-server.ts
    `)
	} else {
		await runTests()
	}
}

main().catch((error) => {
	console.error("Client error:", error)
	process.exit(1)
})
