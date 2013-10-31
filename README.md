autolex
=======

Automatic translations with Google Translate

(N.B. AutoLex was my undergraduate thesis project. It has not been updated since 2011. Since AutoLex was created, Google Translate's terms of service have changed and its API has been restricted. AutoLex stores translations in a database, which may be a violation of the ToS. Usage of this application is not recommended.)

AutoLex translates dynamic content on websites that use the Django web framework. It retrieves translations from the Google Translate service, stores them in a database using a single table, and serves them via a user-defined accessor. In doing so, AutoLex offers website owners a fast, cheap way to translate large amounts of content and to enable multilingual communication between users. Future improvements will include automated accessors, hooks for integration with caching applications, and improved translation generation and display.

For complete documentation, see the thesis document (Ellison_thesis_final.pdf).
