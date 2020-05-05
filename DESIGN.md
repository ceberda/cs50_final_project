
# Background

Getting a clear view into your finances can be difficult, especially for people that have accounts at multiple banks. 

I created a website, called Jesse.  Jesse is a personal financial management tool that provides a user with a holistic view of their finances by letting a user link all their bank accounts in one place.  A user can find their  accounts balances per account and aggregated total on the dashboard.  A user can also view their transaction history for the last 30 days across all accounts Finally, a user can view their monthly spend bucketed across different categorize.  The user can set budgets against each category and check in each month to see if they are on track.  If the user spent more than what he/she budgeted, the row will be highlighted in red.  


# Specification
*Why Jesse?*
-  I knew I wanted a character as the face of my personal financial management tool.  Someone that could interact with the user on my website, to make it feel more human.  I found free SVG images of a business women illustration online (https://profile.freepik.com), in various poses you can see on my website.  
- Next I needed a name.  I wanted a name that tied back to finance, wealth or money.  The site was going to be called Plutus (the Greek god of wealth).  But looked for more modern names and found Jesse (a Hebrew baby meaning wealthy).  

*How does Jesse work?*

 **1. User Registration**

In register.html the user inputs their information to sign up for Jesse. The user must enter their first name, last name, username, password, and confirmation of password.  

When the form is submitted, this information is INSERT(ed) into the users table in the database.  The password is hashed to ensure that it is not stored in plain text in the database.  

Error messages: 
- All input fields are required (part of the html), if user does not enter data,  error message on input box is returned.  I also check these fields are present in `app.py` and return `apology.html` as a fall back.
- If the username already exists, return `apology.html`.
- If passwords do not match, the return `apology.html`.

** 2. Login** 
- If the user clicks on the log in page (GET), the `login.html` is rendered where the user can enter their username and password.
- Check the database if username exist and password is correct for the given user 
- If checks are successful, the user is taken to the homepage (`index.html`) 

** 3.  Dashboard/Accounts** 
*Empty state of the page (A user with no linked accounts)* 
- For this state of the page, I implemented a bootstrap class I found online called [jumotron](https://getbootstrap.com/docs/4.0/components/jumbotron/).  I wanted to make a strong introduction and show the user's first name on the screen, so I implemented a "`Welcome, {{user.firstname}}!`".  
- Also, I thought the call to action was clear that the user had to add their bank accounts to get started.

 *Plaid integration:* 
 - Jesse uses [Plaid](https://plaid.com/) to retrieve the customer's bank data.  Plaid is an API service that acts as the connection layer between Jesse and the user's bank.  I signed up for Plaid's sandbox and needed to incorporate their code into `app.py` in order to get account, balance and transaction data.  
 - On click of 'Link Bank Account',  Jesse redirects the user to Plaid.  The customer then follows the steps by consenting for Plaid to get their data, selects their bank from the list, signs in (using test username and password), and clicks continue.  Then Plaid gets the data from the bank (in the US this is actually done through screen scraping).  While Jesse the website waits for the data I show the spinner on the dashboard.  Once the data comes back from Plaid, I save the data in the database. 
- In order to get data back from Plaid, a token exchange needs to take place (this is to ensure the data is kept secure). Plaid provides the Jesse front end a public token for each 'item' (item = user + institution_id).  
	- The front-end the passes this public token to the Jesse back end, where it exchanges this public token for an 'access token'. It does this by sending both the public token and secure API token to Plaid. 
	- The backend then stores this access token in the database (in the `financial_institution` table).  This token does not expire. 
	- The access token + secure API token can then be used to access the data for that item (e.g. transactions) and going forward when the user refreshes the data.  

*Assumptions*: 
- To keep things simple and knowing I was only getting test data back from Plaid's sandbox I filtered and only stored data for checking and saving (`account['subtype'] in ('checking', 'savings')`)
- I assumed the user could only have one token per financial institution.  Therefore if a user tries to add the same bank again, return an error.  In order to do this, I need to check the institution_id for a given user_id already exist. If it doesn't, then I can store the data in the database.  If it already exist, return an error. 
- If Plaid takes too long to give a website the data, it will return some of the data and then tell the website when the rest of the data is available.  For example, the transaction data can take a few minutes to get back, however, the Jesse dashboard actually doesn't need any transaction data.  So this would be a great feature to have built into the site to reduce the wait time for the user.  However, the logic seemed a bit too complex to decide when I needed to call back out to Plaid.  Therefore, I increased the retry tries from the default so the user will wait until all the data is available.

*Data is returned by Plaid and stored in the Jesse database*
- Store account data in accounts table
- Store bank data in financial institution table
- Store required transaction data in transactions table
- Store list of top level categories as default for budgets table

The Plaid transaction API required me to send a start date and end date.  In order to do this I needed to calculate a date. The budget page requires all the transaction from the previous month and the transaction page requires the last 30 days.  Therefore, I calculated the start date = the the first day of last month and the end date = today. 

*Display data on the dashboard*
- When the user has linked 1 or more accounts the empty state of the dashboard is transformed to display the user their bank account information
- The user can see the account balance across all bank accounts 
- Below they can see the breakdown per bank (sorted by bank name) 
- A user can see their account name, mask #, type of account and current balance per account 

*Refresh* 
- The user can see when their data per bank was last updated by looking at the timestamp
- The user can refresh their data at anytime by clicking refresh
- On click, Jesse will call out to Plaid to get data for the given user and the institution
- When the data is returned, I delete the data for the given user and the institution, then I insert the new data 

**4. Transactions**

*The empty state* 
* Empty state of the page informs the user to check back once they have added account 

*If transaction data exist* 
- The display to the last 30 days of transactions history across all the linked accounts 
- Sorted by the most recent transaction on top

**5. Budgeting**

*The empty state* 
* Empty state of the page informs the user to check back once they have added account 

*If the user has accounts*

 Display in a table:
- List of categories 
- Last month spend per category across all link accounts 
- Budget: the user can set a budget per each category and click save.  The budget is stored in the database, budget table.  The user does not have to set a budget for each category, it can be left null.  
- The user can see how last month spend compares to their budget.  If the user goes over budget, then the row will highlight in red.  I am using a bootstrap class table-danger to style the rows using my bootstrap theme. 

Thanks for exploring my website Jesse! 