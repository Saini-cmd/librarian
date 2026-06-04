# QA Response
- Repo: lynko
- Mode: external

## Question
tell me about the schema and database used in the project in tabular form

## Answer
Based on the provided code excerpts, the project uses **MongoDB** as its database, accessed via a custom `connectDB` helper (`@/lib/mongodb`). The data model is defined in `@/models/Design` (imported as `Design`). Although the full model file is not shown, the code reveals the structure through usage.

| Aspect | Details |
|--------|---------|
| **Database** | MongoDB (NoSQL) |
| **Connection** | `connectDB()` from `@/lib/mongodb` |
| **Model** | `Design` (Mongoose model) |
| **Schema fields (inferred)** | `clerkUserId` (String, used for user lookup)<br>`customization` (Object, stores design settings) |
| **Customization object fields** | `theme` (string, default `"lemonade"`)<br>`font` (string, default `"inter"`)<br>`size` (number, default `2`)<br>`radius` (number, default `2`)<br>`border` (string, default `"none"`)<br>`avatar` (string, default `"rounded-xl"`)<br>`background` (string, default `"bg-primary"`)<br>`buttonStyle` (string, default `"btn btn btn-accent"`)<br>`buttonRadius` (string, default `"rounded"`) |

The `defaultDesign` object in `route.js` ([C2]) likely mirrors the expected shape of the `customization` sub-document in the MongoDB collection. The `Design.findOne({ clerkUserId: userId })` query implies that `clerkUserId` is indexed or at least used as a lookup field.
