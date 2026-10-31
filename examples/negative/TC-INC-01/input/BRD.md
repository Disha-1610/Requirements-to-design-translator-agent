# MiniBank Business Requirements Document

## 1. Introduction
### 1.1 Purpose
Define the requirements for MiniBank, a synthetic retail banking simulation. No real money or real identity data is handled.
### 1.2 Audience
Design, coding and test teams.
### 1.3 References
BR-001, BR-002, BR-003 in Section 6.
### 1.4 Acronyms and Glossary
BRD: Business Requirements Document. KYC: Know Your Customer.

## 2. Project Drivers
### 2.1 Business Problem
Customers need a simple way to view balances and move money between accounts.
### 2.2 Business Objectives
Allow secure login, balance viewing and transfers.
### 2.3 Stakeholders
Customers, operations team.

## 3. Constraints, Assumptions and Dependencies
### 3.1 Constraints
Synthetic data only.
### 3.2 Assumptions
Customers already hold one active account.
### 3.3 Dependencies
None.

## 4. Current State
Customers use branch visits only.

## 5. Scope of Work
### 5.1 In Scope for v1
- Customer login
- Balance viewing
- Fund transfer between accounts
### 5.2 Out of Scope for v1
- Cryptocurrency trading
- Loan origination
- International wire transfers
### 5.3 Roles
Customer.

## 6. Business Rules
- BR-001: A transfer amount must not exceed the available balance.
- BR-002: A customer may view the balance of their own accounts.
- BR-003: A customer must authenticate before any account action.

## 9. Issues
None open.

## 10. Handover
Hand over to the Design Agent after approval.
