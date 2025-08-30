# 40k_memo_maker

## Introduction
This app is used to create a cheat sheet for a 40k game.  
The app has a DB of yaml files containing the informations regarding the different units of an army, but also strategic informations about unitts and when they should be activated or do something.  
Based on those files and on an export from 40k android app, the app will create an html file containing :
- the details of each units in the team
- A schedule of every rounf phase and which unit should be doing what in each phase

## Yaml scheme
*file_descriptor.yml*

## StreamLit
The app can be deployed on StreamLit : just copy the files and you're done

### Streamlit specifics
- App can choose from own yaml files or uploaded yaml files
- 40k export can be uploaded has text file or copy/paste
- HTML is being diplayed and can be downloaded too
