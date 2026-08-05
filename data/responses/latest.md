# QA Response
- Repo: to-do-list

## Question
give an overview of the project

## Answer
## Project Overview

This is a **console-based Java To-Do List application** that uses `LinkedList` to manage tasks [C1]. It supports **add, view, remove, and mark-as-done** operations through a simple menu-driven interface [C2].

### Features
- Add tasks with a name and deadline [C2]
- Mark tasks as completed [C2]
- Remove tasks by name [C2]
- Display all tasks or only incomplete tasks [C2]

### File Structure
```
to-do-list/
├── MainFile.java    # Entry point with menu loop and task management logic
└── Task.java        # Data model for a single task
```
[C1]

### Key Implementation Details
- **`MainFile.java`** holds a `LinkedList<Task>` and static methods (`addTask`, `removeTask`, `markTaskDone`, `display`, `displayAllUncompleted`). The main loop presents a menu (choices 1–5) and runs indefinitely [C2].
- **`Task.java`** encapsulates `taskName`, `deadLine`, and `isCompleted` (initially `false`). Exposes getters and `setIsCompleted()` (sets to `true`). `toString()` returns a checkbox-style string (e.g., `[✗] — Buy groceries — (Deadline 2024-12-31)`) [C3].
- No external dependencies; requires only JDK to compile and run [C1].

### How to Run
```
javac MainFile.java
java MainFile
```
[C1]
