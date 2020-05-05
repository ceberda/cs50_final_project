# Jesse Finance (CS50 Final Project)

Getting a clear view into your finances can be difficult, especially for people that have accounts at multiple banks. Jesse is here to help!

-----

## Package Management & Environment Setup

This project uses ``pipenv`` to configure the runtime environment and package downloads. 

If you don't have ``pipenv`` installed, head to their [install page](https://pipenv-fork.readthedocs.io/en/latest/#install-pipenv-today) and install it before continuing. 

## Plaid API Access

Jesse makes extensive use of [Plaid](http://plaid.com/) to get account and transaction data. To use Jesse, you will need to sign up for access to a sandbox account with Plaid. 

Steps:

* Go to: https://dashboard.plaid.com/signup
* Sign up for an account (choose 'Personal Finances' for 'What are you building?')
* Plaid will have sent you and email to verify your account. Please do so. 
* Go to: https://dashboard.plaid.com/team/keys (Team Settings -> Keys)
* We will be using the `client_id`, `public_key` and the Sandbox secret for Jesse.

NOTE: the Sandbox environment never has any real data and will never ask you login with your real bank details. Don't be fooled by the real bank names!

### Token envrionment variables

When running Jesse we set the Plaid API keys via environment variables. You can do this once per shell using `export` or prepend them the command to start the server (see below). 

    PLAID_CLIENT_ID = <client_id>
    PLAID_PUBLIC_KEY = <public_key>
    PLAID_SECRET = <Sandbox secret>

## Running Jesse Locally

If this is the first time you are running Jesse after checkout, you will need to download the 3rd party packages using `pipenv`:

    $ pipenv install

To run Jesse locally, we need to setup the environment first using `pipenv`:

    $ pipenv shell

Then we can run Jesse using the following command, substituting your Plaid API keys:

    $ PLAID_CLIENT_ID=? PLAID_SECRET=? PLAID_PUBLIC_KEY=? FLASK_ENV=development flask run --without-threads

(if you have already exported the Plaid keys, you do not need to include them in this command). 

Jesse should now startup on http://localhost:5000! Head to the 'Getting Started' page to sign up for an account. 
