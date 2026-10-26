# Focus Tracker — Artifact 3 Development Log

**Project:** Focus Tracker — AI-Powered Productivity Dashboard  
**Course Assignment:** Artifact 3 — AI Tool Integration  
**Development Tools:** Claude Code and ChatGPT  
**Purpose of this log:** Document what I planned, what changed throughout development, and how the application evolved while working with Claude Code.

> **Record accuracy:** This log was assembled from my planning discussions with ChatGPT, interactions with Claude Code, and the results I observed throughout development. It is a retrospective summary of the development process rather than a transcript of individual AI prompts.

## 1. Project Planning and Scope

**Planned:** For Artifact 3, I wanted to expand my previous Focus Tracker project into a fully functional web application with AI-powered productivity insights. I considered several other project ideas but ultimately decided to build upon Artifact 2, making it more accessible and useful to a wider audience.

**Changed / Outcome:** I decided to preserve the existing Python CLI functionality while developing a web application using FastAPI. I organized development into three main phases: building the website foundation, implementing interactive session tracking, and integrating the Claude API for personalized weekly insights.

## 2. Web Application Foundation and Design

**Planned:** Create a modern, responsive website with a sleek dark theme, vibrant colors, interactive navigation, hover animations, and an option to switch to light mode. I wanted the design to feel different from my personal portfolio while remaining intuitive and easy to navigate.

**Changed / Outcome:** Claude implemented the initial web application using FastAPI, HTML, CSS, and JavaScript. The application included a productivity dashboard and navigation between focus sessions, activities, history, and AI Insights. After reviewing the initial implementation, I made adjustments to the interface and overall user experience before moving on to the next phase.

## 3. Interactive Session Tracking

**Planned:** Make the website fully functional by allowing users to manage activities, start focus sessions, control timers, and record additional information about their productivity. I also wanted completed sessions to automatically update the dashboard and session history.

**Changed / Outcome:** Claude implemented interactive focus timers, activity management, session history, and the ability to record locations, distractions, and reflections. Users could also add, edit, and delete sessions. I tested these features and confirmed that completed sessions appeared in the history and updated the dashboard statistics. The web application continued to share the existing JSON storage with the original CLI.

## 4. Claude API Integration and Refinements

**Planned:** Integrate the Claude API to analyze recorded focus sessions and generate personalized weekly productivity insights. I wanted the reports to identify focus patterns, common distractions, strengths, areas for improvement, and recommendations for the following week.

**Changed / Outcome:** Claude implemented the AI Insights feature using the Anthropic API. During testing, I encountered an error that prevented the page from loading, which Claude helped resolve. After generating several reports, I noticed that the analysis was somewhat lengthy and repetitive, so I worked with Claude to make it more concise while preserving meaningful observations and recommendations. We also refined how the AI handled limited data to avoid drawing overly confident conclusions.

## 5. Public Deployment and Browser Storage

**Planned:** Initially, the application was designed to run locally, but I wanted to make it accessible to my professor, friends, and other visitors without requiring installation. I decided to attempt a temporary deployment using Render Free.

**Changed / Outcome:** Since the original JSON storage wasn't suitable for multiple public visitors, Claude implemented a separate demo mode using browser localStorage. Each visitor could interact with their own sample data, track sessions, and generate real AI insights without affecting other users. We also added API usage limits and security measures to protect the Claude integration. I deployed the application through Render and verified that the interactive features, browser storage, and AI-generated reports worked successfully.

## 6. Final Result and Future Improvements

**Final Result:** Artifact 3 successfully expanded my original command-line Focus Tracker into a fully functional web application with interactive focus sessions, productivity dashboards, activity management, and AI-powered weekly insights. The application is also publicly accessible through a temporary Render deployment.

**Future Improvements:** I would like to continue expanding the application with additional productivity features, more reliable hosting, persistent database storage, and potentially user accounts. I could also see myself eventually developing a mobile version of Focus Tracker.

**Live Demo:** [Focus Tracker](https://focus-tracker-demo.onrender.com)
