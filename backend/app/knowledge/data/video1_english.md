# Video 1: How to Fill the App Scoping Details in the Scoping Document

**URL:** https://www.youtube.com/watch?v=YNBf2V2VzUE
**Source:** Avni Launchpad How-to Guide Series, Tutorial #2
**Example Program:** Phulwari (Community-run creche/daycare for children 6 months to 3 years)
**Topics:** Forms, Visit Scheduling, App Offline Dashboard Cards, User Permissions

---

## Transcript (Transliterated from Devanagari to English)

Welcome. In this video we will walk you through how to complete the remaining components of the scoping document. In today's video we will be covering the Forms, Visit Scheduling, your App Offline Dashboard Cards, and the User Permissions.

To help you understand the scoping document, I will be taking the example of the Phulwari program scoping document.

For those who are new, to give a context about the Phulwari program: Phulwari program is a community-run creche/daycare initiative that takes care of young children, typically from the age of six months to three years. It is designed to combat under-nutrition, improve the health and early development, and provide a safe childcare environment to the children while their parents are working.

So, let's get started. If you see the first step, it's the Help and Status Tracker which will act as a guide for you to fill the remaining elements of the scoping document. So it gives you the component, covers the tab, each of the columns present in those tabs, and what does it mean — like a description. So, for example, the Form tabs? There are different columns and what are these columns and what they mean? You can refer to it while you are filling the form sheet.

### FORMS

Let's start with the Forms.

Forms — take them as a tool your users will be using to enter information into the system. The forms ensure that all the data collection is in a consistent, well-structured, and digital-ready format.

Now let's take the example of the Phulwari program. If you see the W3H, Phulwari has these elements and these are the forms they have: **Child Registration, Child Enrollment, Anthropometry Assessment, Daily Attendance, and a Child Exit.** Now what information are you collecting in the Child Registration — that gets captured in the Form tabs. OK? So first form is your Child Registration.

#### Column: Page Name

In this, the first column is the **Page Name**. Page Name meaning — so what you can do is, based on the information you are collecting, you can name the page. So, for example, the first few questions where we are collecting the information about the child, so you can name the page as "Child Details". Then the remaining details are about the parents, so you can name it as "Parents Details". So this is the Page Name.

#### Column: Field Name

Next comes your **Field Name** which you can take it as the question. Like for here it's the First Name, Last Name of the child, Date of Birth, Age, Gender, then your address/location where the child belongs to, then the Father details — Father's Name, Mother's Name, Occupation, their Contact Number. This is the Field Name.

#### Column: Data Type

Next is your **Data Types**. So in Avni there are different ways you can collect different types of data. You can collect — for example, when you enter a name, that's a **Text** — you will be entering. When it's a Date of Birth — it's a **Date** data type. Age is **Numeric**. Then you have something called **Pre-added Options** (Coded) where you can — like for example, Gender — you can give options as Male, Female, Other — and the user can select it. They don't have to manually enter it. Those options can be pre-coded in the system and the user while using the application, they can select it. So we have Pre-added Options.

So here if you see, you will see the list of data types. Anyone from them — depending on what kind of question, what kind of information you are collecting, you can select. So sometimes if you need to collect **Images** or **Files**, you have that option as well. So here Data Type you can specify that.

#### Column: Mandatory

**Mandatory** — Yes/No — meaning if Mandatory is Yes, without collecting that information, you can't save or complete the form. So these are the information that needs to be there in the form for you to save it.

**On Avni, we really suggest to make most of the questions mandatory**, because if it's non-mandatory, they can skip that question and save the form — which almost means like not having that question. But unless there are certain scenarios where you know the field user while entering the data will not have that particular information — unless it's that scenario, **we suggest making all the questions mandatory**.

#### Column: User Enter / System Generated

Next is your **User Enter / System Generated**. So in Avni, if there is — for example, if you go to the Anthropometry/Child Anthropometry — so Height and Weight is something — it's a Numeric data type which the user will enter. **Based on the Height and Weight, the BMI of the child, the system will automatically calculate.** So that is how you can define the user type. So the things that your user will be manually entering, and what you want — if there's certain information you want the system to generate based on your previously entered values and input — that you can specify in the User Enter/System column.

#### Column: Numeric Validation (Negative, Decimal, Min/Max, Unit)

Next is — so if the Data Type is Numeric, we are to ensure the data quality is maintained. We collect more information like if it's a Numeric data type — **whether to allow negative value or decimal value**. For example, Age can not be negative and can not be a decimal, so we have marked it as No.

Similarly, to again maintain the data quality/data hygiene, you can specify the **maximum-minimum limit**. So for example, it's a child program, so your maximum age is six years. So the user by mistake doesn't enter 600 — to maintain that hygiene you can maintain a maximum-minimum limit.

You can specify the **Unit** — for example, if you are collecting monthly income or the weight, you can specify whether it should be INR or it's a KG — that unit can be specified in this column.

#### Column: Date Type

**Date Type** — meaning when you select the Data Type as Date, you can specify whether to allow current date, future date, or past date — depending on what information you are collecting.

#### Column: Pre-added Options (Single/Multi Select)

**Pre-added Options** — here when the Data Type is Pre-added (Coded), you can tell us whether that information needs to be a **Single-Select** question or a **Multi-Select**. For example, Gender — this is a Single Select, so one of the options from Male, Female, Other you can select. Like for Occupation, it's a Single Select.

Similarly, there will be — for example, in the Child Enrollment, they have a question of Disability which is a **Multi-Select** — there are multiple options. A person might have multiple disabilities. You can select that in Multi-Select question.

#### Column: Unique Options

There is something called **Unique Options**. So for example, here if someone selects "None", he or she will not be able to select any of the disability — because None means the person doesn't have a disability. So they will not be allowed to select any other disability.

#### Column: Skip Logic (Show When / Not Show When)

Then you have **When to Show / When Not to Show** (Skip Logic). Like here, if the Disability is Yes, you show this. If the Disability is No, then you don't show this. OK?

So this is how you fill. So for each of the elements — like Child Registration was one form. You create a sheet here in this format, you fill the details. Similarly, the next form, you create a tab and fill the details. So that's how you need to fill your form details here.

### VISIT SCHEDULING

Next we move to the **Visit Scheduling**.

With this, we tell us how the system — how a certain activity in your program takes place. Like for example, in the Phulwari program, they have the Child Assessment — so they do the monthly Child Anthropometry on a monthly basis. Like the Daily Attendance, they take on a daily basis. So the **Visit Scheduling tab will tell us when a particular form needs to be scheduled**.

The columns present here are:
- **On Completion Of** — which form triggers the schedule
- **Schedule Form** — which form gets scheduled
- **Frequency** — how often (monthly, daily, quarterly, yearly)
- **Schedule For** — which user type (from User Persona tab)
- **Condition to Schedule** — when to schedule
- **Condition NOT to Schedule** — when not to schedule
- **Schedule Date** — specific date (e.g., first of every month)
- **Overdue Date** — when it becomes overdue
- **What happens if you Cancel the visit**
- **What happens if the visit falls on a Weekend/Holiday**
- **On Edit** — what happens when a form is edited

#### Example: Anthropometry Assessment

So this Anthropometry Assessment in the Phulwari program happens on a monthly basis. So once the child is enrolled in the program, **on completion of Child Enrollment, the form that will be scheduled is your Child Anthropometry Assessment**. This Anthropometry Assessment — the **frequency is Monthly**. And it is scheduled for the Phulwari (user type from User Persona tab).

**Condition to Schedule:** We schedule this Anthropometry when the child is enrolled into the Phulwari program.

**When NOT to Schedule:** For example, if the child dies, or there is a permanent migration, or child is over the program age — you don't schedule this form.

**Schedule Date:** Since it's a monthly activity, this form will be scheduled at the **first of every month**. You can specify if there is something quarterly happening or yearly happening.

#### Overdue

**Due/Overdue** is basically — when you select a due date, say from the first of every month, this form on the user's mobile application, it will start showing as "Due". Like this visit is due. You need to go and do the Child Anthropometry on the first of every month. It will show as Due.

**When it reaches 15th, this due visit will become Overdue.** It will be like a warning for the Phulwari user that "OK, I had to complete this visit before 15th. Now I have crossed it." So it's Overdue. It's like a warning and an urgent scenario for them where you need to complete that visit.

#### Cancellation

If a visit is cancelled — so for example, the child is temporarily gone somewhere, or when the Phulwari visits at the child's home, the person was not there, the child was not there — he or she can cancel that visit. So you can give a scenario — **what happens if you cancel that visit**. If you cancel it, then the next visit should get scheduled as per the next month. Or maybe the Phulwari should have an option to select a [new date].

#### Weekend/Holiday

If a visit falls on a weekend or holiday — if your team doesn't work on weekends — what happens? **It should be scheduled on the next following working day.**

#### On Edit

And sometimes once you fill the form, if the user has permission to edit the information (if they have made some mistake) — **on Edit, what should happen — should the next visit get scheduled on the same day? Or no impact should happen on edit.** So that you can specify here.

### APP DASHBOARD (Offline Dashboard Cards)

**App Dashboards** — which we also call Mobile Dashboards or Offline Dashboards — are the dashboard when the user logs in to the Avni application, they see at the home screen. So this will guide you, gives you a gist of what's happening in your program — like what actions or activities that need to be done by that particular user.

So for example, in this particular program, there are Phulwari users who will be using the Avni application for collecting data about the beneficiaries. They will be doing their regular Anthropometry visits.

**For them, when they log in to the application — think of this while filling this sheet — think of this in that perspective: for the Phulwari user group, which information when they see on that mobile application will help them do their activity better.**

So for them in this program, for the Phulwari user group, they wanted to capture information like:
- **Number of Children Enrolled** — how many of the children registered have been enrolled into the Phulwari program
- **Scheduled Anthropometry Visits** — how many visits are scheduled
- **Cancelled Visits** — how many have been cancelled

So the card gives you: **Card Name** and the **Logic/Eligibility** (or logic to show in the card) and you can specify the **User Type**.

The User Type here — this card is for the Phulwari users, also for the Supervisor. So when the User Type comes from your User Persona sheet — whatever user type you mentioned there, you can specify it in this particular tab.

So the next one is — since they have a regular Anthropometry on a monthly basis, it will be useful for the Phulwari users to know how many Anthropometry visits have been scheduled. How many out of these scheduled visits have been cancelled by them. So they also know — this keeps the Phulwari also tracking: "I have to do 10 visits, out of this I had cancelled five." They can analyze. Even the Supervisor when they see, they will know — they can do an analysis of why these cancellations are happening.

### USER PERMISSIONS

Next comes your **Permissions**. Permissions meaning — for each of the forms, and for each of your User Types, you can give them certain permissions and certain privileges based on what activity they will be doing on the ground.

For example, here in the Phulwari program, these are the user groups they have: **Phulwari, Supervisor, Doctor, Administrator** — and these are the forms.

**Child Registration** — if you see, the Phulwari will be allowed to **View** the particular form, they will be allowed to **Register** the child, they can **Edit** if they made some mistake, they can edit that.

**Void** here means **Delete**. So in layman's terms, Avni we use the word "Void" but in layman's terms it means Delete. So whether they will be able to delete once a child is registered — do we need some approval from the Supervisor? So all those things you can specify.

Similarly, a Supervisor might not be filling/doing a Child Registration. For that you can make it "No". Like for example, a **Doctor will not be doing a Child Registration**. So for him, everything is marked as No — **he will just be viewing it**. So you give the permission as Yes [for view only].

So accordingly you can specify — for each of the forms and activities you do, what are the permissions to each of these users you need to assign.

---

So that's it for today's video. I hope this video helps you understand how to fill these components — the Forms, Visit Scheduling, and User Permissions section in the scoping document. We will be coming up with more such explainer videos. Thank you so much. Hope you find this video useful. Thank you.
